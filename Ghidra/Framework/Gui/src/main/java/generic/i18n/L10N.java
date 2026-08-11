/* ###
 * IP: GHIDRA
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package generic.i18n;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

import generic.jar.ResourceFile;
import ghidra.framework.Application;

/**
 * Display-time string localization.
 * <p>
 * Ghidra has no message catalog; every user-visible string is a hardcoded Java literal, and many
 * of those literals double as identifiers (key binding keys, {@code .tool} file entries, menu bar
 * ordering).  Translating the literals in place would therefore break saved user state.  Instead,
 * a small number of <em>rendering</em> call sites route their text through {@link #tr(String)},
 * so the English string remains the identifier while the user sees a translation.
 * <p>
 * Nothing happens unless the {@code ghidra.i18n} system property names a locale, so a single build
 * serves as both the English and the localized product:
 *
 * <pre>
 * ghidraRun -Dghidra.i18n=zh_CN
 * </pre>
 *
 * Translations live in {@code &lt;module&gt;/data/i18n/&lt;locale&gt;.properties} (UTF-8), optionally
 * overridden per-user by {@code &lt;user settings&gt;/i18n/&lt;locale&gt;.properties}.  Any string with no
 * entry is displayed unchanged, so an untranslated build degrades to English rather than failing.
 * <p>
 * Setting {@code ghidra.i18n.dump} to a file path records every string that had no translation,
 * which is how the catalog is kept current as upstream adds and changes text.
 */
public class L10N {

	/** System property naming the locale to display, e.g. {@code zh_CN}.  Absent means English. */
	public static final String LOCALE_PROPERTY = "ghidra.i18n";

	/** System property naming a file to record untranslated strings into. */
	public static final String DUMP_PROPERTY = "ghidra.i18n.dump";

	/** Value of {@link #LOCALE_PROPERTY} that explicitly disables translation. */
	private static final String DISABLED = "off";

	private static final String MODULE_DATA_PATH = "i18n/%s.properties";
	private static final String USER_SETTINGS_DIR = "i18n";

	private static volatile Map<String, String> dictionary;
	private static Set<String> misses;

	private L10N() {
		// utility class
	}

	/**
	 * Translates a user-visible string for display.
	 * <p>
	 * This is a display-time conversion only.  Never feed the result back into anything that
	 * stores, compares or looks up the value - the untranslated string is the identifier.
	 *
	 * @param text the English text, as written in the source; may be null
	 * @return the translation, or {@code text} unchanged when translation is disabled or no
	 *         catalog entry exists
	 */
	public static String tr(String text) {
		if (text == null || text.isBlank()) {
			return text;
		}

		Map<String, String> map = getDictionary();
		if (map.isEmpty()) {
			return text;
		}

		// HTML is matched whole; picking mnemonics out of markup would corrupt it
		if (isHtml(text)) {
			return lookup(map, text, text);
		}

		// Most call sites receive text that MenuData has already stripped, but a raw literal can
		// reach here too; the catalog is keyed on plain text either way.
		return lookup(map, stripMnemonic(text), text);
	}

	/**
	 * Translates a user-visible string that carries a separate mnemonic, such as a menu item.
	 * <p>
	 * Swing underlines a mnemonic by finding that character in the displayed text, so a
	 * translation that no longer contains it would silently lose its keyboard hint.  When that
	 * happens the accelerator is appended in parentheses - the established convention for CJK
	 * menus - giving Swing a character to underline:  {@code Search} with mnemonic {@code S}
	 * becomes {@code 搜索(S)}.
	 *
	 * @param text the English text, as written in the source; may be null
	 * @param mnemonic the mnemonic character; anything non-positive means none, which covers both
	 *        an absent character and {@code MenuData.NO_MNEMONIC}
	 * @return the translation carrying a visible mnemonic, or {@code text} unchanged when
	 *         translation is disabled or no catalog entry exists
	 */
	public static String tr(String text, int mnemonic) {
		String translated = tr(text);
		if (translated == null || translated.equals(text)) {
			return translated; // untranslated text still contains its own mnemonic
		}
		if (mnemonic <= 0 || mnemonic > Character.MAX_VALUE || isHtml(translated)) {
			return translated;
		}
		if (indexOfIgnoreCase(translated, (char) mnemonic) >= 0) {
			return translated; // Swing already has a character to underline
		}
		return translated + "(" + Character.toUpperCase((char) mnemonic) + ")";
	}

	/**
	 * @return true if a locale is configured and its catalog was found
	 */
	public static boolean isEnabled() {
		return !getDictionary().isEmpty();
	}

	private static int indexOfIgnoreCase(String text, char c) {
		char lower = Character.toLowerCase(c);
		for (int i = 0; i < text.length(); i++) {
			if (Character.toLowerCase(text.charAt(i)) == lower) {
				return i;
			}
		}
		return -1;
	}

	private static String lookup(Map<String, String> map, String key, String defaultValue) {
		String translated = map.get(key);
		if (translated == null) {
			recordMiss(key);
			return defaultValue;
		}
		return translated;
	}

	private static boolean isHtml(String text) {
		return text.length() >= 6 && text.regionMatches(true, 0, "<html", 0, 5);
	}

	//==================================================================================================
	// Mnemonics
	//==================================================================================================

	/**
	 * Removes the mnemonic markers from text, mirroring the {@code MenuData} convention where a
	 * single {@code &} marks the next character as the mnemonic and {@code &&} is a literal
	 * ampersand.
	 *
	 * @param text the text
	 * @return the text with mnemonic markers removed
	 */
	private static String stripMnemonic(String text) {
		if (text.indexOf('&') < 0) {
			return text;
		}

		StringBuilder buffy = new StringBuilder(text.length());
		for (int i = 0; i < text.length(); i++) {
			char c = text.charAt(i);
			if (c != '&') {
				buffy.append(c);
				continue;
			}
			if (i + 1 < text.length() && text.charAt(i + 1) == '&') {
				buffy.append('&');
				i++; // consume the escaped pair
			}
			// a lone '&' is the marker itself and is dropped
		}
		return buffy.toString();
	}

	//==================================================================================================
	// Catalog loading
	//==================================================================================================

	/**
	 * Installs a catalog directly, bypassing {@link Application} and the system properties.
	 * <p>
	 * Public so that tests in the modules that own the hooked call sites can drive it; the
	 * translation itself happens in Docking, one module downstream of here.
	 *
	 * @param catalog the translations, or null to restore normal lazy loading
	 */
	public static void setCatalogForTesting(Map<String, String> catalog) {
		dictionary = catalog == null ? null : Map.copyOf(catalog);
	}

	private static Map<String, String> getDictionary() {
		Map<String, String> map = dictionary;
		if (map == null) {
			synchronized (L10N.class) {
				map = dictionary;
				if (map == null) {
					map = loadDictionary();
					dictionary = map;
				}
			}
		}
		return map;
	}

	private static Map<String, String> loadDictionary() {
		String locale = System.getProperty(LOCALE_PROPERTY);
		if (locale == null || locale.isBlank() || DISABLED.equalsIgnoreCase(locale)) {
			return Map.of();
		}

		// Application owns module discovery and the user settings directory.  Before it comes up
		// there is no UI to translate, so stay disabled rather than guessing at paths.
		if (!Application.isInitialized()) {
			return Map.of();
		}

		Map<String, String> map = new HashMap<>();
		readInto(map, findModuleCatalog(locale));
		readInto(map, findUserCatalog(locale)); // user entries win
		if (map.isEmpty()) {
			return Map.of();
		}

		installDumper();
		return map;
	}

	private static ResourceFile findModuleCatalog(String locale) {
		return Application.findDataFileInAnyModule(String.format(MODULE_DATA_PATH, locale));
	}

	private static ResourceFile findUserCatalog(String locale) {
		File settings = Application.getUserSettingsDirectory();
		if (settings == null) {
			return null;
		}
		File file = new File(new File(settings, USER_SETTINGS_DIR), locale + ".properties");
		return file.isFile() ? new ResourceFile(file) : null;
	}

	private static void readInto(Map<String, String> map, ResourceFile file) {
		if (file == null || !file.exists()) {
			return;
		}

		// Properties.load(InputStream) is ISO-8859-1; the Reader overload is required for UTF-8
		Properties properties = new Properties();
		try (Reader reader =
			new InputStreamReader(file.getInputStream(), StandardCharsets.UTF_8)) {
			properties.load(reader);
		}
		catch (IOException e) {
			// Msg lives downstream of this module, and a missing translation must never be fatal
			System.err.println("L10N: unable to read translations from " + file + ": " + e);
			return;
		}

		for (String name : properties.stringPropertyNames()) {
			String value = properties.getProperty(name);
			if (!value.isBlank()) {
				map.put(name, value);
			}
		}
	}

	//==================================================================================================
	// Missing string collection
	//==================================================================================================

	private static void recordMiss(String key) {
		Set<String> set = misses;
		if (set != null) {
			set.add(key);
		}
	}

	private static void installDumper() {
		String path = System.getProperty(DUMP_PROPERTY);
		if (path == null || path.isBlank()) {
			return;
		}

		misses = ConcurrentHashMap.newKeySet();
		File file = new File(path);
		Runtime.getRuntime().addShutdownHook(new Thread(() -> dumpMisses(file), "L10N Dump"));
	}

	private static void dumpMisses(File file) {
		Set<String> set = misses;
		if (set == null || set.isEmpty()) {
			return;
		}

		List<String> keys = new ArrayList<>(set);
		Collections.sort(keys);
		try (PrintWriter writer = new PrintWriter(
			new OutputStreamWriter(new FileOutputStream(file), StandardCharsets.UTF_8))) {
			writer.println("# Strings displayed with no translation available.");
			writer.println("# Add a value to each entry and merge into the locale catalog.");
			for (String key : keys) {
				writer.println(escape(key) + "=");
			}
		}
		catch (IOException e) {
			System.err.println("L10N: unable to write " + file + ": " + e);
		}
	}

	/**
	 * Escapes a string for use as a .properties key.
	 *
	 * @param key the key
	 * @return the escaped key
	 */
	private static String escape(String key) {
		StringBuilder buffy = new StringBuilder(key.length());
		for (int i = 0; i < key.length(); i++) {
			char c = key.charAt(i);
			switch (c) {
				// every space is escaped: an unescaped one would terminate the key
				case '=', ':', '#', '!', '\\', ' ' -> buffy.append('\\').append(c);
				case '\t' -> buffy.append("\\t");
				case '\n' -> buffy.append("\\n");
				case '\r' -> buffy.append("\\r");
				default -> buffy.append(c);
			}
		}
		return buffy.toString();
	}
}
