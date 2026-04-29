#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic;
bool deviceConnected = false;

const int sensorPin = 0;
const int mosfetPin = 1;

bool isAutoMode = true;
int currentOffset = 0;
int manualBrightness = 0;
unsigned long lastSendTime = 0;

#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        deviceConnected = true;
    };

    void onDisconnect(BLEServer* pServer) {
        deviceConnected = false;
        pServer->getAdvertising()->start();
        Serial.println("Отключено. Жду новых подключений...");
    }
};

class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        String rxValue = pCharacteristic->getValue().c_str();
        rxValue.trim();

        if (rxValue.length() > 0) {
            char mode = rxValue.charAt(0);
            int val = rxValue.substring(1).toInt();

            if (mode == 'A') {
                isAutoMode = true;
                currentOffset = val;
            }
            else {
                isAutoMode = false;
                manualBrightness = constrain(val, 0, 255);
            }
        }
    }
};

void setup() {
    Serial.begin(115200);
    pinMode(mosfetPin, OUTPUT);

    BLEDevice::init("ESP32_SmartLamp");
    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    BLEService *pService = pServer->createService(SERVICE_UUID);

    pTxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_TX,
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pTxCharacteristic->addDescriptor(new BLE2902());

    BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_RX,
        BLECharacteristic::PROPERTY_WRITE
    );
    pRxCharacteristic->setCallbacks(new MyCallbacks());

    pService->start();
    pServer->getAdvertising()->start();
}

void loop() {
    int brightness = 0;
    int currentLight = analogRead(sensorPin);

    if (isAutoMode) {
        brightness = map(currentLight, 0, 4095, 255, 0) + currentOffset;
    } else {
        brightness = manualBrightness;
    }

    brightness = constrain(brightness, 0, 255);
    analogWrite(mosfetPin, brightness);

    if (deviceConnected && (millis() - lastSendTime > 1000)) {
        String message = String(currentLight) + "-" + String(brightness);
        pTxCharacteristic->setValue(message.c_str());
        pTxCharacteristic->notify();
        lastSendTime = millis();
    }

    delay(20);
}