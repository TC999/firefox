/* Any copyright is dedicated to the Public Domain.
   http://creativecommons.org/publicdomain/zero/1.0/ */

"use strict";

/**
 * This test is checking the fallbacks when an engine that is default is
 * removed or hidden.
 *
 * The fallback procedure is:
 *
 * - Region/Locale default (if visible)
 * - First visible engine
 * - If no other visible engines, unhide the region/locale default and use it.
 */

let appDefault;
let appPrivateDefault;

const CONFIG = [
  { identifier: "default", base: { classification: "unknown" } },
  { identifier: "defaultPrivate", base: { classification: "unknown" } },
  { identifier: "generalEngine", base: { classification: "general" } },
  { identifier: "otherEngine", base: { classification: "unknown" } },
  {
    globalDefault: "default",
    globalDefaultPrivate: "defaultPrivate",
  },
];

add_setup(async function () {
  useHttpServer();
  SearchTestUtils.setRemoteSettingsConfig(CONFIG);

  Services.prefs.setCharPref(SearchUtils.BROWSER_SEARCH_PREF + "region", "US");
  Services.prefs.setBoolPref(
    SearchUtils.BROWSER_SEARCH_PREF + "separatePrivateDefault.ui.enabled",
    true
  );
  Services.prefs.setBoolPref(
    SearchUtils.BROWSER_SEARCH_PREF + "separatePrivateDefault",
    true
  );

  appDefault = await Services.search.getDefault();
  appPrivateDefault = await Services.search.getDefaultPrivate();
});

function getDefault(privateMode) {
  return privateMode
    ? Services.search.getDefaultPrivate()
    : Services.search.getDefault();
}

function setDefault(privateMode, engine) {
  return privateMode
    ? Services.search.setDefaultPrivate(
        engine,
        Ci.nsISearchService.CHANGE_REASON_UNKNOWN
      )
    : Services.search.setDefault(
        engine,
        Ci.nsISearchService.CHANGE_REASON_UNKNOWN
      );
}

async function checkFallbackDefaultRegion(checkPrivate) {
  let defaultEngine = checkPrivate ? appPrivateDefault : appDefault;
  let expectedDefaultNotification = checkPrivate
    ? SearchUtils.MODIFIED_TYPE.DEFAULT_PRIVATE
    : SearchUtils.MODIFIED_TYPE.DEFAULT;
  Services.search.restoreDefaultEngines();

  let otherEngine = Services.search.getEngineByName("otherEngine");
  await setDefault(checkPrivate, otherEngine);

  Assert.notEqual(
    otherEngine,
    defaultEngine,
    "Sanity check engines are different"
  );

  const observer = new SearchObserver(
    [
      expectedDefaultNotification,
      // For hiding (removing) the engine.
      SearchUtils.MODIFIED_TYPE.CHANGED,
      SearchUtils.MODIFIED_TYPE.REMOVED,
    ],
    expectedDefaultNotification
  );

  await Services.search.removeEngine(otherEngine);

  let notified = await observer.promise;

  Assert.ok(otherEngine.hidden, "Should have hidden the removed engine");
  Assert.equal(
    (await getDefault(checkPrivate)).name,
    defaultEngine.name,
    "Should have reverted the defaultEngine to the region default"
  );
  Assert.equal(
    notified.name,
    defaultEngine.name,
    "Should have notified the correct default engine"
  );
}

add_task(async function test_default_fallback_to_region_default() {
  await checkFallbackDefaultRegion(false);
});

add_task(async function test_default_private_fallback_to_region_default() {
  await checkFallbackDefaultRegion(true);
});

async function checkFallbackFirstVisible(checkPrivate) {
  let defaultEngine = checkPrivate ? appPrivateDefault : appDefault;
  let expectedDefaultNotification = checkPrivate
    ? SearchUtils.MODIFIED_TYPE.DEFAULT_PRIVATE
    : SearchUtils.MODIFIED_TYPE.DEFAULT;
  Services.search.restoreDefaultEngines();

  let otherEngine = Services.search.getEngineByName("otherEngine");
  await setDefault(checkPrivate, otherEngine);
  await Services.search.removeEngine(defaultEngine);

  Assert.notEqual(
    otherEngine,
    defaultEngine,
    "Sanity check engines are different"
  );

  const observer = new SearchObserver(
    checkPrivate
      ? [
          expectedDefaultNotification,
          // For hiding (removing) the engine.
          SearchUtils.MODIFIED_TYPE.CHANGED,
          SearchUtils.MODIFIED_TYPE.REMOVED,
        ]
      : [
          expectedDefaultNotification,
          // For hiding (removing) the engine.
          SearchUtils.MODIFIED_TYPE.CHANGED,
          SearchUtils.MODIFIED_TYPE.REMOVED,
        ],
    expectedDefaultNotification
  );

  await Services.search.removeEngine(otherEngine);

  let notified = await observer.promise;

  Assert.equal(
    (await getDefault(checkPrivate)).name,
    "generalEngine",
    "Should have set the default engine to the first visible general engine"
  );
  Assert.equal(
    notified.name,
    "generalEngine",
    "Should have notified the correct default general engine"
  );
}

add_task(async function test_default_fallback_to_first_gen_visible() {
  await checkFallbackFirstVisible(false);
});

add_task(async function test_default_private_fallback_to_first_gen_visible() {
  await checkFallbackFirstVisible(true);
});

// Removing all visible engines affects both the default and private default
// engines.
add_task(async function test_default_fallback_when_no_others_visible() {
  // Remove all but one of the visible engines.
  let visibleEngines = await Services.search.getVisibleEngines();
  for (let i = 0; i < visibleEngines.length - 1; i++) {
    await Services.search.removeEngine(visibleEngines[i]);
  }
  Assert.equal(
    (await Services.search.getVisibleEngines()).length,
    1,
    "Should only have one visible engine"
  );

  const observer = new SearchObserver(
    [
      // Unhiding of the default engine.
      SearchUtils.MODIFIED_TYPE.CHANGED,
      // Change of the default.
      SearchUtils.MODIFIED_TYPE.DEFAULT,
      // Unhiding of the default private.
      SearchUtils.MODIFIED_TYPE.CHANGED,
      SearchUtils.MODIFIED_TYPE.DEFAULT_PRIVATE,
      // Hiding the engine.
      SearchUtils.MODIFIED_TYPE.CHANGED,
      SearchUtils.MODIFIED_TYPE.REMOVED,
    ],
    SearchUtils.MODIFIED_TYPE.DEFAULT
  );

  // Now remove the last engine, which should set the new default.
  await Services.search.removeEngine(visibleEngines[visibleEngines.length - 1]);

  let notified = await observer.promise;

  Assert.equal(
    (await getDefault(false)).name,
    appDefault.name,
    "Should fallback to the app default engine after removing all engines"
  );
  Assert.equal(
    (await getDefault(true)).name,
    appPrivateDefault.name,
    "Should fallback to the app default private engine after removing all engines"
  );
  Assert.equal(
    notified.name,
    appDefault.name,
    "Should have notified the correct default engine"
  );
  Assert.ok(
    !appPrivateDefault.hidden,
    "Should have unhidden the app default private engine"
  );
  Assert.equal(
    (await Services.search.getVisibleEngines()).length,
    2,
    "Should now have two engines visible"
  );
});

add_task(async function test_default_fallback_remove_default_no_visible() {
  // Remove all but the default engine.

  await Services.search.setDefaultPrivate(
    Services.search.defaultEngine,
    Ci.nsISearchService.CHANGE_REASON_UNKNOWN
  );
  let visibleEngines = await Services.search.getVisibleEngines();
  for (let engine of visibleEngines) {
    if (engine.name != appDefault.name) {
      await Services.search.removeEngine(engine);
    }
  }
  Assert.equal(
    (await Services.search.getVisibleEngines()).length,
    1,
    "Should only have one visible engine"
  );

  const observer = new SearchObserver(
    [
      // Unhiding of the default engine.
      SearchUtils.MODIFIED_TYPE.CHANGED,
      // Change of the default.
      SearchUtils.MODIFIED_TYPE.DEFAULT,
      SearchUtils.MODIFIED_TYPE.DEFAULT_PRIVATE,
      // Hiding the engine.
      SearchUtils.MODIFIED_TYPE.CHANGED,
      SearchUtils.MODIFIED_TYPE.REMOVED,
    ],
    SearchUtils.MODIFIED_TYPE.DEFAULT
  );

  // Now remove the last engine, which should set the new default.
  await Services.search.removeEngine(appDefault);

  let notified = await observer.promise;

  Assert.equal(
    (await getDefault(false)).name,
    "generalEngine",
    "Should fallback the default engine to the first general search engine"
  );
  Assert.equal(
    (await getDefault(true)).name,
    "generalEngine",
    "Should fallback the default private engine to the first general search engine"
  );
  Assert.equal(
    notified.name,
    "generalEngine",
    "Should have notified the correct default engine"
  );
  Assert.ok(
    !Services.search.getEngineByName("generalEngine").hidden,
    "Should have unhidden the new engine"
  );
  Assert.equal(
    (await Services.search.getVisibleEngines()).length,
    1,
    "Should now have one engines visible"
  );
});

add_task(
  async function test_default_fallback_remove_default_no_visible_or_general() {
    Services.search.restoreDefaultEngines();

    // For this test, we need to change any general search engines to unknown,
    // so that we can test what happens in the unlikely event that there are no
    // general search engines.
    let searchConfig = structuredClone(CONFIG);
    for (let entry of searchConfig) {
      if (entry.base?.classification == "general") {
        entry.base.classification = "unknown";
      }
    }
    SearchTestUtils.setRemoteSettingsConfig(searchConfig);
    Services.search.wrappedJSObject.reset();
    await Services.search.init();

    appPrivateDefault = await Services.search.getDefaultPrivate();

    await Services.search.setDefault(
      appPrivateDefault,
      Ci.nsISearchService.CHANGE_REASON_UNKNOWN
    );

    // Remove all but the default engine.
    let visibleEngines = await Services.search.getVisibleEngines();
    for (let engine of visibleEngines) {
      if (engine.name != appPrivateDefault.name) {
        await Services.search.removeEngine(engine);
      }
    }
    Assert.deepEqual(
      (await Services.search.getVisibleEngines()).map(e => e.name),
      appPrivateDefault.name,
      "Should only have one visible engine"
    );

    const observer = new SearchObserver(
      [
        // Unhiding of the default engine.
        SearchUtils.MODIFIED_TYPE.CHANGED,
        // Change of the default.
        SearchUtils.MODIFIED_TYPE.DEFAULT,
        SearchUtils.MODIFIED_TYPE.DEFAULT_PRIVATE,
        // Hiding the engine.
        SearchUtils.MODIFIED_TYPE.CHANGED,
        SearchUtils.MODIFIED_TYPE.REMOVED,
      ],
      SearchUtils.MODIFIED_TYPE.DEFAULT
    );

    // Now remove the last engine, which should set the new default.
    await Services.search.removeEngine(appPrivateDefault);

    let notified = await observer.promise;

    Assert.equal(
      (await getDefault(false)).name,
      "default",
      "Should fallback to the first engine that isn't a general search engine"
    );
    Assert.equal(
      (await getDefault(true)).name,
      "default",
      "Should fallback the private engine to the first engine that isn't a general search engine"
    );
    Assert.equal(
      notified.name,
      "default",
      "Should have notified the correct default engine"
    );
    Assert.ok(
      !Services.search.getEngineByName("default").hidden,
      "Should have unhidden the new engine"
    );
    Assert.equal(
      (await Services.search.getVisibleEngines()).length,
      1,
      "Should now have one engines visible"
    );
  }
);

// Test the other remove engine route - for removing non-application provided
// engines.

async function checkNonBuiltinFallback(checkPrivate) {
  let defaultEngine = checkPrivate ? appPrivateDefault : appDefault;
  let expectedDefaultNotification = checkPrivate
    ? SearchUtils.MODIFIED_TYPE.DEFAULT_PRIVATE
    : SearchUtils.MODIFIED_TYPE.DEFAULT;
  Services.search.restoreDefaultEngines();

  let addedEngine = await SearchTestUtils.installOpenSearchEngine({
    url: `${gHttpURL}/opensearch/generic2.xml`,
  });

  await setDefault(checkPrivate, addedEngine);

  const observer = new SearchObserver(
    [expectedDefaultNotification, SearchUtils.MODIFIED_TYPE.REMOVED],
    expectedDefaultNotification
  );

  // Remove the current engine...
  await Services.search.removeEngine(addedEngine);

  // ... and verify we've reverted to the normal default engine.
  Assert.equal(
    (await getDefault(checkPrivate)).name,
    defaultEngine.name,
    "Should revert to the app default engine"
  );

  let notified = await observer.promise;
  Assert.equal(
    notified.name,
    defaultEngine.name,
    "Should have notified the correct default engine"
  );
}

add_task(async function test_default_fallback_non_builtin() {
  await checkNonBuiltinFallback(false);
});

add_task(async function test_default_fallback_non_builtin_private() {
  await checkNonBuiltinFallback(true);
});
