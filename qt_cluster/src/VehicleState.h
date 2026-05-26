#pragma once

#include <QJsonObject>
#include <QObject>
#include <QTimer>

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
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(qlonglong lastUpdateMs READ lastUpdateMs NOTIFY lastUpdateMsChanged)

public:
    explicit VehicleState(QObject* parent = nullptr);

    double speed() const;
    double odometer() const;
    double trip() const;
    QString source() const;
    QString stateFile() const;
    int pollMs() const;
    int profileMaxSpeed() const;
    QString profileUnit() const;
    bool connected() const;
    QString lastError() const;
    qlonglong lastUpdateMs() const;

    void setSpeed(double value);
    void setOdometer(double value);
    void setTrip(double value);
    void setSource(const QString& value);
    void setStateFile(const QString& value);
    void setPollMs(int value);
    void setProfileMaxSpeed(int value);
    void setProfileUnit(const QString& value);

    Q_INVOKABLE void loadStateNow();

signals:
    void speedChanged();
    void odometerChanged();
    void tripChanged();
    void sourceChanged();
    void stateFileChanged();
    void pollMsChanged();
    void profileMaxSpeedChanged();
    void profileUnitChanged();
    void connectedChanged();
    void lastErrorChanged();
    void lastUpdateMsChanged();

private:
    void updatePolling();
    void applyJson(const QJsonObject& obj);
    void setConnected(bool value);
    void setLastError(const QString& value);
    void setLastUpdateMs(qlonglong value);

    double m_speed = 23.0;
    double m_odometer = 87266.0;
    double m_trip = 0.0;
    QString m_source = "demo";
    QString m_stateFile = "../state.json";
    int m_pollMs = 120;
    int m_profileMaxSpeed = 260;
    QString m_profileUnit = "km/h";
    bool m_connected = false;
    QString m_lastError;
    qlonglong m_lastUpdateMs = 0;
    QTimer m_pollTimer;
};
