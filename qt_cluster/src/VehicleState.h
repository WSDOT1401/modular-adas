#pragma once

#include <QJsonObject>
#include <QObject>
#include <QTimer>
#include <QUdpSocket>

class VehicleState : public QObject {
    Q_OBJECT
    Q_PROPERTY(double speed READ speed WRITE setSpeed NOTIFY speedChanged)
    Q_PROPERTY(double odometer READ odometer WRITE setOdometer NOTIFY odometerChanged)
    Q_PROPERTY(double trip READ trip WRITE setTrip NOTIFY tripChanged)
    Q_PROPERTY(QString source READ source WRITE setSource NOTIFY sourceChanged)
    Q_PROPERTY(QString stateFile READ stateFile WRITE setStateFile NOTIFY stateFileChanged)
    Q_PROPERTY(int pollMs READ pollMs WRITE setPollMs NOTIFY pollMsChanged)
    Q_PROPERTY(int profileMaxSpeed READ profileMaxSpeed WRITE setProfileMaxSpeed NOTIFY profileMaxSpeedChanged)
    Q_PROPERTY(QString profileUnit READ profileUnit WRITE setProfileUnit NOTIFY profileUnitChanged)
    Q_PROPERTY(QString profilePage READ profilePage WRITE setProfilePage NOTIFY profilePageChanged)
    Q_PROPERTY(QString speedSource READ speedSource WRITE setSpeedSource NOTIFY speedSourceChanged)
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(qlonglong lastUpdateMs READ lastUpdateMs NOTIFY lastUpdateMsChanged)
    Q_PROPERTY(QString carplayStatus READ carplayStatus NOTIFY carplayStatusChanged)
    Q_PROPERTY(double oilTemp READ oilTemp NOTIFY oilTempChanged)
    Q_PROPERTY(double outsideTemp READ outsideTemp NOTIFY outsideTempChanged)
    Q_PROPERTY(double voltage READ voltage NOTIFY voltageChanged)

public:
    explicit VehicleState(QObject* parent = nullptr);
    ~VehicleState();

    double speed() const;
    double odometer() const;
    double trip() const;
    QString source() const;
    QString stateFile() const;
    int pollMs() const;
    int profileMaxSpeed() const;
    QString profileUnit() const;
    QString profilePage() const;
    QString speedSource() const;
    bool connected() const;
    QString lastError() const;
    qlonglong lastUpdateMs() const;
    QString carplayStatus() const;
    double oilTemp() const;
    double outsideTemp() const;
    double voltage() const;

    void setSpeed(double value);
    void setOdometer(double value);
    void setTrip(double value);
    void setSource(const QString& value);
    void setStateFile(const QString& value);
    void setPollMs(int value);
    void setProfileMaxSpeed(int value);
    void setProfileUnit(const QString& value);
    void setProfilePage(const QString& value);
    void setSpeedSource(const QString& value);
    void setUdpPort(int port);

    Q_INVOKABLE void loadStateNow();
    Q_INVOKABLE void resetTrip();

signals:
    void speedChanged();
    void odometerChanged();
    void tripChanged();
    void sourceChanged();
    void stateFileChanged();
    void pollMsChanged();
    void profileMaxSpeedChanged();
    void profileUnitChanged();
    void profilePageChanged();
    void speedSourceChanged();
    void connectedChanged();
    void lastErrorChanged();
    void lastUpdateMsChanged();
    void carplayStatusChanged();
    void oilTempChanged();
    void outsideTempChanged();
    void voltageChanged();

private:
    void updatePolling();
    void applyJson(const QJsonObject& obj);
    void integrateDistanceNow();
    void saveDistanceNow();
    void setConnected(bool value);
    void setLastError(const QString& value);
    void setLastUpdateMs(qlonglong value);
    void setCarplayStatus(const QString& value);
    void setOilTemp(double value);
    void setOutsideTemp(double value);
    void setVoltage(double value);
    void loadCarplayStatusNow();
    void onUdpDataReady();

    double m_speed = 23.0;
    double m_odometer = 87266.0;
    double m_trip = 0.0;
    QString m_source = "demo";
    QString m_stateFile = "../state.json";
    int m_pollMs = 16;   // ~60 Hz — match display frame rate for smooth needle
    int m_profileMaxSpeed = 260;
    QString m_profileUnit = "km/h";
    QString m_profilePage = "classic";
    QString m_speedSource = "OBD";
    bool m_connected = false;
    QString m_lastError;
    qlonglong m_lastUpdateMs = 0;
    qlonglong m_lastIntegrateMs = 0;
    bool m_externalDistanceAuthoritative = false;
    QString m_carplayStatus = QStringLiteral("waiting");
    double m_oilTemp = -1.0;
    double m_outsideTemp = -999.0;
    double m_voltage = 0.0;
    int m_udpPort = 9100;
    QTimer m_pollTimer;
    QTimer m_integrateTimer;
    QTimer m_saveTimer;
    QTimer m_carplayPollTimer;
    QUdpSocket m_udpSocket;
};
