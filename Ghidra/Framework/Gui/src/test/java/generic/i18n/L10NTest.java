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

import static org.junit.Assert.*;

import java.util.Map;

import org.junit.After;
import org.junit.Test;

public class L10NTest {

	private static final int NO_MNEMONIC = -1; // matches docking.action.MenuData

	@After
	public void tearDown() {
		L10N.setCatalogForTesting(null);
	}

	@Test
	public void testDisabledByDefault() {
		// no catalog installed and no locale property: text must pass through untouched
		assertEquals("Search", L10N.tr("Search"));
		assertFalse(L10N.isEnabled());
	}

	@Test
	public void testTranslatesKnownText() {
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		assertEquals("搜索", L10N.tr("Search"));
		assertTrue(L10N.isEnabled());
	}

	@Test
	public void testUnknownTextFallsBackToEnglish() {
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		assertEquals("Some New Upstream Action", L10N.tr("Some New Upstream Action"));
	}

	@Test
	public void testNullAndBlankAreLeftAlone() {
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		assertNull(L10N.tr(null));
		assertEquals("   ", L10N.tr("   "));
	}

	@Test
	public void testMnemonicMarkersAreStrippedBeforeLookup() {
		// a raw literal can reach tr() before MenuData has processed it
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		assertEquals("搜索", L10N.tr("&Search"));
	}

	@Test
	public void testEscapedAmpersandIsNotAMnemonic() {
		L10N.setCatalogForTesting(Map.of("Cut & Paste", "剪切和粘贴"));
		assertEquals("剪切和粘贴", L10N.tr("Cut && Paste"));
	}

	@Test
	public void testMnemonicIsAppendedWhenTranslationLosesIt() {
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		// Swing underlines by finding the character in the text, so it must remain present
		assertEquals("搜索(S)", L10N.tr("Search", 'S'));
	}

	@Test
	public void testMnemonicNotAppendedWhenAlreadyPresent() {
		L10N.setCatalogForTesting(Map.of("Search", "Search 搜索"));
		assertEquals("Search 搜索", L10N.tr("Search", 'S'));
	}

	@Test
	public void testNoMnemonicSentinelIsIgnored() {
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		assertEquals("搜索", L10N.tr("Search", NO_MNEMONIC));
		assertEquals("搜索", L10N.tr("Search", 0));
	}

	@Test
	public void testUntranslatedTextKeepsItsOwnMnemonic() {
		L10N.setCatalogForTesting(Map.of("Search", "搜索"));
		assertEquals("&Edit", L10N.tr("&Edit", 'E'));
	}

	@Test
	public void testHtmlIsMatchedWhole() {
		L10N.setCatalogForTesting(Map.of("<html><b>Show", "<html><b>显示"));
		assertEquals("<html><b>显示", L10N.tr("<html><b>Show"));
	}

	@Test
	public void testHtmlNeverGetsAMnemonicSuffix() {
		L10N.setCatalogForTesting(Map.of("<html>Search", "<html>搜索"));
		assertEquals("<html>搜索", L10N.tr("<html>Search", 'S'));
	}
}
