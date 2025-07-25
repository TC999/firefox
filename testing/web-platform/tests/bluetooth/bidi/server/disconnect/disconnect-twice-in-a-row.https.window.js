// META: script=/resources/testdriver.js?feature=bidi
// META: script=/resources/testdriver-vendor.js
// META: script=/bluetooth/resources/bluetooth-test.js
// META: script=/bluetooth/resources/bluetooth-fake-devices.js
// META: timeout=long
'use strict';
const test_desc = 'Calling disconnect twice in a row still results in ' +
    '\'connected\' being false.';

// TODO(569716): Test that the disconnect signal was sent to the device.
bluetooth_bidi_test(async () => {
  let {device, fake_peripheral} = await getDiscoveredHealthThermometerDevice();
  await fake_peripheral.setNextGATTConnectionResponse({
    code: HCI_SUCCESS,
  });
  let gattServer = await device.gatt.connect();
  await gattServer.disconnect();
  assert_false(gattServer.connected);
  await gattServer.disconnect();
  assert_false(gattServer.connected);
}, test_desc);
