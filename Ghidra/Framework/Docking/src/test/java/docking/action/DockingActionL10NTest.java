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
package docking.action;

import static org.junit.Assert.*;

import java.util.Map;

import javax.swing.JMenuItem;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import docking.ActionContext;
import generic.i18n.L10N;

/**
 * Guards the menu text hooks.
 * <p>
 * Menu item text is set in two places: here in {@link DockingAction#createMenuItem(boolean)},
 * which is what a menu renders through the first time, and again in
 * {@code MenuItemManager.updateMenuItem}, which only runs when an action's menu data changes
 * afterwards. Hooking one and not the other looks fine in a catalog check and fails only when
 * someone opens a menu, so both paths are asserted.
 */
public class DockingActionL10NTest {

	private static final String ITEM = "Delete Tool";
	private static final String TRANSLATED = "删除工具";

	private DockingAction action;

	@Before
	public void setUp() {
		L10N.setCatalogForTesting(Map.of(ITEM, TRANSLATED, "Tools", "工具"));
		action = new DockingAction(ITEM, "test") {
			@Override
			public void actionPerformed(ActionContext context) {
				// nothing to do; this action exists only to carry menu data
			}
		};
	}

	@After
	public void tearDown() {
		L10N.setCatalogForTesting(null);
	}

	@Test
	public void testCreatedMenuItemIsTranslated() {
		action.setMenuBarData(new MenuData(new String[] { "&Tools", ITEM }));
		JMenuItem menuItem = action.createMenuItem(false);
		assertEquals(TRANSLATED, menuItem.getText());
	}

	@Test
	public void testPopupMenuItemIsTranslated() {
		action.setPopupMenuData(new MenuData(new String[] { "&Tools", ITEM }));
		JMenuItem menuItem = action.createMenuItem(true);
		assertEquals(TRANSLATED, menuItem.getText());
	}

	@Test
	public void testMnemonicStaysVisible() {
		// Swing underlines a mnemonic by finding the character in the text, so a translation
		// that drops it has to gain a visible one
		action.setMenuBarData(new MenuData(new String[] { "&Tools", "&" + ITEM }));
		JMenuItem menuItem = action.createMenuItem(false);
		assertEquals(TRANSLATED + "(D)", menuItem.getText());
	}

	@Test
	public void testUntranslatedItemKeepsEnglish() {
		String unknown = "No Such Menu Item";
		action.setMenuBarData(new MenuData(new String[] { "&Tools", unknown }));
		JMenuItem menuItem = action.createMenuItem(false);
		assertEquals(unknown, menuItem.getText());
	}

	@Test
	public void testActionNameIsNotTranslated() {
		// the name is an identifier: key bindings and saved tools are stored under it
		action.setMenuBarData(new MenuData(new String[] { "&Tools", ITEM }));
		action.createMenuItem(false);
		assertEquals(ITEM, action.getName());
	}
}
