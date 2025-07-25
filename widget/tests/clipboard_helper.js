/* Any copyright is dedicated to the Public Domain.
   http://creativecommons.org/publicdomain/zero/1.0/ */

"use strict";

const Cc = SpecialPowers.Cc;
const Ci = SpecialPowers.Ci;
const Cr = SpecialPowers.Cr;
const clipboard = SpecialPowers.Services.clipboard;
const clipboardTypes = [
  clipboard.kGlobalClipboard,
  clipboard.kSelectionClipboard,
  clipboard.kFindClipboard,
  clipboard.kSelectionCache,
];

async function getWindowProtocol() {
  return await SpecialPowers.spawnChrome([], () => {
    try {
      return Cc["@mozilla.org/gfx/info;1"].getService(Ci.nsIGfxInfo)
        .windowProtocol;
    } catch {
      return "";
    }
  });
}

async function emptyClipboardData(aType) {
  // XXX gtk doesn't support emptying clipboard data which is stored from
  // other application (bug 1853884). As a workaround, we set dummy data
  // to the clipboard first to ensure the subsequent emptyClipboard call
  // works.
  if (navigator.platform.includes("Linux")) {
    writeStringToClipboard("foo", "text/plain", aType);
  }

  clipboard.emptyClipboard(aType);

  // Give some time for GTK to process owner change callback.
  await new Promise(resolve => SimpleTest.executeSoon(resolve));
  // XXX wayland does not support clearing clipboard, see bug 1857075.
  if ((await getWindowProtocol()) !== "wayland") {
    let snapshot = getClipboardDataSnapshotSync(aType);
    isDeeply(snapshot.flavorList, [], "Clipboard should be empty");
  }
}

async function cleanupAllClipboard() {
  for (let type of clipboardTypes) {
    if (clipboard.isClipboardTypeSupported(type)) {
      info(`cleanup clipboard ${type}`);
      await emptyClipboardData(type);
    }
  }
}

function generateRandomString() {
  return "random number: " + Math.random();
}

function generateNewTransferable(aFlavor, aStr) {
  let trans = Cc["@mozilla.org/widget/transferable;1"].createInstance(
    Ci.nsITransferable
  );
  trans.init(null);
  trans.addDataFlavor(aFlavor);

  let supportsStr = Cc["@mozilla.org/supports-string;1"].createInstance(
    Ci.nsISupportsString
  );
  supportsStr.data = aStr;
  trans.setTransferData(aFlavor, supportsStr);

  return trans;
}

function addStringToTransferable(aFlavor, aStr, aTrans) {
  aTrans.addDataFlavor(aFlavor);

  let supportsStr = Cc["@mozilla.org/supports-string;1"].createInstance(
    Ci.nsISupportsString
  );
  supportsStr.data = aStr;
  aTrans.setTransferData(aFlavor, supportsStr);
}

function updateStringToTransferable(aFlavor, aStr, aTrans) {
  let supportsStr = Cc["@mozilla.org/supports-string;1"].createInstance(
    Ci.nsISupportsString
  );
  supportsStr.data = aStr;
  aTrans.setTransferData(aFlavor, supportsStr);
}

function writeStringToClipboard(
  aStr,
  aFlavor,
  aClipboardType,
  aClipboardOwner = null,
  aAsync = false
) {
  let trans = Cc["@mozilla.org/widget/transferable;1"].createInstance(
    Ci.nsITransferable
  );
  trans.init(null);
  trans.addDataFlavor(aFlavor);

  let supportsStr = Cc["@mozilla.org/supports-string;1"].createInstance(
    Ci.nsISupportsString
  );
  supportsStr.data = aStr;
  trans.setTransferData(aFlavor, supportsStr);

  if (aAsync) {
    let request = clipboard.asyncSetData(aClipboardType);
    request.setData(trans, aClipboardOwner);
    return;
  }

  clipboard.setData(trans, aClipboardOwner, aClipboardType);
  // XXX gtk doesn't support get empty text data from clipboard, bug 1852983.
  if (aStr == "" && navigator.platform.includes("Linux")) {
    todo_is(
      getClipboardData(aFlavor, aClipboardType),
      "",
      `Should get empty string on clipboard type ${aClipboardType}`
    );
  } else {
    is(
      getClipboardData(aFlavor, aClipboardType),
      // On Windows, widget adds extra data into HTML clipboard.
      aFlavor == "text/html" && navigator.platform.includes("Win")
        ? `<html><body>\n<!--StartFragment-->${aStr}<!--EndFragment-->\n</body>\n</html>`
        : aStr,
      "ensure clipboard data is set"
    );
  }
}

function writeRandomStringToClipboard(
  aFlavor,
  aClipboardType,
  aClipboardOwner = null,
  aAsync = false
) {
  let randomString = generateRandomString();
  writeStringToClipboard(
    randomString,
    aFlavor,
    aClipboardType,
    aClipboardOwner,
    aAsync
  );
  return randomString;
}

function getClipboardData(aFlavor, aClipboardType) {
  var trans = Cc["@mozilla.org/widget/transferable;1"].createInstance(
    Ci.nsITransferable
  );
  trans.init(null);
  trans.addDataFlavor(aFlavor);
  clipboard.getData(
    trans,
    aClipboardType,
    SpecialPowers.wrap(window).browsingContext.currentWindowContext
  );

  try {
    var data = SpecialPowers.createBlankObject();
    trans.getTransferData(aFlavor, data);
    return data.value.QueryInterface(SpecialPowers.Ci.nsISupportsString).data;
  } catch (ex) {
    // If the clipboard is empty getTransferData will throw.
    return null;
  }
}

function getClipboardDataSnapshotSync(aClipboardType) {
  return clipboard.getDataSnapshotSync(
    ["text/plain", "text/html", "image/png"],
    aClipboardType
  );
}

function getClipboardDataSnapshot(
  aClipboardType,
  aFormats = ["text/plain", "text/html", "image/png"]
) {
  return new Promise((resolve, reject) => {
    try {
      clipboard.getDataSnapshot(
        aFormats,
        aClipboardType,
        null,
        SpecialPowers.Services.scriptSecurityManager.getSystemPrincipal(),
        {
          QueryInterface: SpecialPowers.ChromeUtils.generateQI([
            "nsIClipboardGetDataSnapshotCallback",
          ]),
          // nsIClipboardGetDataSnapshotCallback
          onSuccess: SpecialPowers.wrapCallback(
            function (aAsyncGetClipboardData) {
              resolve(aAsyncGetClipboardData);
            }
          ),
          onError: SpecialPowers.wrapCallback(function (aResult) {
            reject(aResult);
          }),
        }
      );
    } catch (e) {
      ok(false, `getDataSnapshot should not throw`);
      reject(e);
    }
  });
}

function asyncClipboardRequestGetData(aRequest, aFlavor, aThrows = false) {
  return new Promise((resolve, reject) => {
    var trans = Cc["@mozilla.org/widget/transferable;1"].createInstance(
      Ci.nsITransferable
    );
    trans.init(null);
    trans.addDataFlavor(aFlavor);
    try {
      aRequest.getData(trans, aResult => {
        if (aResult != Cr.NS_OK) {
          reject(aResult);
          return;
        }

        try {
          var data = SpecialPowers.createBlankObject();
          trans.getTransferData(aFlavor, data);
          resolve(data.value.QueryInterface(Ci.nsISupportsString).data);
        } catch (ex) {
          // XXX: should widget set empty string to transferable when there no
          // data in system clipboard?
          resolve("");
        }
      });
      ok(
        !aThrows,
        `nsIAsyncGetClipboardData.getData should ${
          aThrows ? "throw" : "success"
        }`
      );
    } catch (e) {
      ok(
        aThrows,
        `nsIAsyncGetClipboardData.getData should ${
          aThrows ? "throw" : "success"
        }`
      );
      reject(e.result);
    }
  });
}

function syncClipboardRequestGetData(aRequest, aFlavor, aResult = Cr.NS_OK) {
  var trans = Cc["@mozilla.org/widget/transferable;1"].createInstance(
    Ci.nsITransferable
  );
  trans.init(null);
  trans.addDataFlavor(aFlavor);
  let result = Cr.NS_OK;
  try {
    aRequest.getDataSync(trans);
    try {
      var data = SpecialPowers.createBlankObject();
      trans.getTransferData(aFlavor, data);
      return data.value.QueryInterface(Ci.nsISupportsString).data;
    } catch (ex) {
      // should widget set empty string to transferable when there no
      // data in system clipboard?
      return "";
    }
  } catch (e) {
    result = e.result;
  } finally {
    is(
      result,
      aResult,
      `nsIAsyncGetClipboardData.getData should ${aResult == Cr.NS_OK ? "throw" : "success"}`
    );
  }
  return "";
}
