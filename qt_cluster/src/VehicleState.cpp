#include "VehicleState.h"

#include <QDateTime>
#include <QFile>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QSettings>

namespace {
int normalizeProfileMaxSpeed(int value) {
    const int allowed[] = {180, 200, 220, 240, 260, 300};
    for (const int v : allowed) {
        if (v == value) {
            return v;
        }
    }
    return 260;
}

QString normalizeProfileUnit(const QString& value) {
    return value == QStringLiteral("mph") ? QStringLiteral("mph") : QStringLiteral("km/h");
}
}

VehicleState::VehicleState(QObject* parent) : QObject(parent) {
    QSettings settings;
    setProfileMaxSpeed(settings.value(QStringLiteral("gauge/profileMaxSpeed"), m_profileMaxSpeed).toInt());
    setProfileUnit(settings.value(QStringLiteral("gauge/profileUnit"), m_profileUnit).toString());

    connect(&m_pollTimer, &QTimer::timeout, this, &VehicleState::loadStateNow);
    updatePolling();
}

double VehicleState::speed() const { return m_speed; }
double VehicleState::odometer() const { return m_odometer; }
double VehicleState::trip() const { return m_trip; }
QString VehicleState::source() const { return m_source; }
QString VehicleState::stateFile() const { return m_stateFile; }
int VehicleState::pollMs() const { return m_pollMs; }
int VehicleState::profileMaxSpeed() const { return m_profileMaxSpeed; }
QString VehicleState::profileUnit() const { return m_profileUnit; }
bool VehicleState::connected() const { return m_connected; }
QString VehicleState::lastError() const { return m_lastError; }
qlonglong VehicleState::lastUpdateMs() const { return m_lastUpdateMs; }

void VehicleState::setSpeed(double value) {
    if (qFuzzyCompare(m_speed, value)) return;
    m_speed = value;
    emit speedChanged();
}

void VehicleState::setOdometer(double value) {
    if (qFuzzyCompare(m_odometer, value)) return;
    m_odometer = value;
    emit odometerChanged();
}

void VehicleState::setTrip(double value) {
    if (qFuzzyCompare(m_trip, value)) return;
    m_trip = value;
    emit tripChanged();
}

void VehicleState::setSource(const QString& value) {
    if (m_source == value) return;
    m_source = value;
    emit sourceChanged();
    updatePolling();
}

void VehicleState::setStateFile(const QString& value) {
    if (m_stateFile == value) return;
    m_stateFile = value;
    emit stateFileChanged();
}

void VehicleState::setPollMs(int value) {
    const int clamped = qMax(50, value);
    if (m_pollMs == clamped) return;
    m_pollMs = clamped;
    emit pollMsChanged();
    updatePolling();
}

void VehicleState::setProfileMaxSpeed(int value) {
    const int normalized = normalizeProfileMaxSpeed(value);
    if (m_profileMaxSpeed == normalized) return;
    m_profileMaxSpeed = normalized;
    emit profileMaxSpeedChanged();

    QSettings settings;
    settings.setValue(QStringLiteral("gauge/profileMaxSpeed"), m_profileMaxSpeed);
}

void VehicleState::setProfileUnit(const QString& value) {
    const QString normalized = normalizeProfileUnit(value);
    if (m_profileUnit == normalized) return;
    m_profileUnit = normalized;
    emit profileUnitChanged();

    QSettings settings;
    settings.setValue(QStringLiteral("gauge/profileUnit"), m_profileUnit);
}

void VehicleState::updatePolling() {
    if (m_source == "state") {
        m_pollTimer.start(m_pollMs);
        loadStateNow();
    } else {
        m_pollTimer.stop();
        setConnected(false);
        setLastError(QString());
    }
}

void VehicleState::loadStateNow() {
    if (m_source != "state") return;

    QFile file(m_stateFile);
    if (!file.open(QIODevice::ReadOnly)) {
        setConnected(false);
        setLastError(QStringLiteral("Cannot open state file: %1").arg(m_stateFile));
        return;
    }

    QJsonParseError parseError;
    const auto doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
        setConnected(false);
        setLastError(QStringLiteral("Invalid state JSON: %1").arg(parseError.errorString()));
        return;
    }

    applyJson(doc.object());
    setConnected(true);
    setLastError(QString());
    setLastUpdateMs(QDateTime::currentMSecsSinceEpoch());
}

void VehicleState::applyJson(const QJsonObject& obj) {
    if (obj.contains("speed") && obj["speed"].isDouble()) {
        setSpeed(obj["speed"].toDouble());
    }
    if (obj.contains("odo") && obj["odo"].isDouble()) {
        setOdometer(obj["odo"].toDouble());
    }
    if (obj.contains("trip") && obj["trip"].isDouble()) {
        setTrip(obj["trip"].toDouble());
    }
}

void VehicleState::setConnected(bool value) {
    if (m_connected == value) return;
    m_connected = value;
    emit connectedChanged();
}

void VehicleState::setLastError(const QString& value) {
    if (m_lastError == value) return;
    m_lastError = value;
    emit lastErrorChanged();
}

void VehicleState::setLastUpdateMs(qlonglong value) {
    if (m_lastUpdateMs == value) return;
    m_lastUpdateMs = value;
    emit lastUpdateMsChanged();
}
