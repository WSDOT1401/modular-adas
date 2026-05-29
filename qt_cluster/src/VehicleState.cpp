#include "VehicleState.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHostAddress>
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

VehicleState::~VehicleState() {
    saveDistanceNow();
}

VehicleState::VehicleState(QObject* parent) : QObject(parent) {
    QSettings settings;
    setProfileMaxSpeed(settings.value(QStringLiteral("gauge/profileMaxSpeed"), m_profileMaxSpeed).toInt());
    setProfileUnit(settings.value(QStringLiteral("gauge/profileUnit"), m_profileUnit).toString());
    m_profilePage   = settings.value(QStringLiteral("ui/profilePage"),   m_profilePage).toString();
    m_speedSource   = settings.value(QStringLiteral("data/speedSource"), m_speedSource).toString();
    m_odometer = settings.value(QStringLiteral("distance/odometer"), m_odometer).toDouble();
    m_trip     = settings.value(QStringLiteral("distance/trip"),     m_trip).toDouble();

    connect(&m_pollTimer,      &QTimer::timeout, this, &VehicleState::loadStateNow);
    connect(&m_integrateTimer, &QTimer::timeout, this, &VehicleState::integrateDistanceNow);
    connect(&m_saveTimer,      &QTimer::timeout, this, &VehicleState::saveDistanceNow);
    connect(&m_carplayPollTimer, &QTimer::timeout, this, &VehicleState::loadCarplayStatusNow);
    m_integrateTimer.setInterval(50);
    m_lastIntegrateMs = QDateTime::currentMSecsSinceEpoch();
    m_integrateTimer.start();
    m_saveTimer.setInterval(30000);  // persist odo/trip every 30 s
    m_saveTimer.start();
    updatePolling();
}

QString VehicleState::carplayStatus() const { return m_carplayStatus; }

double VehicleState::speed() const { return m_speed; }
double VehicleState::odometer() const { return m_odometer; }
double VehicleState::trip() const { return m_trip; }
QString VehicleState::source() const { return m_source; }
QString VehicleState::stateFile() const { return m_stateFile; }
int VehicleState::pollMs() const { return m_pollMs; }
int VehicleState::profileMaxSpeed() const { return m_profileMaxSpeed; }
QString VehicleState::profileUnit() const { return m_profileUnit; }
QString VehicleState::profilePage() const { return m_profilePage; }
QString VehicleState::speedSource() const { return m_speedSource; }
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
    m_externalDistanceAuthoritative = false;
    m_lastIntegrateMs = QDateTime::currentMSecsSinceEpoch();
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

void VehicleState::setProfilePage(const QString& value) {
    const QString normalized = (value == "music" || value == "map") ? value : "classic";
    if (m_profilePage == normalized) return;
    m_profilePage = normalized;
    emit profilePageChanged();

    QSettings settings;
    settings.setValue(QStringLiteral("ui/profilePage"), m_profilePage);
}

void VehicleState::setSpeedSource(const QString& value) {
    const QString normalized = (value == "GPS") ? QStringLiteral("GPS") : QStringLiteral("OBD");
    if (m_speedSource == normalized) return;
    m_speedSource = normalized;
    emit speedSourceChanged();

    QSettings settings;
    settings.setValue(QStringLiteral("data/speedSource"), m_speedSource);
}

void VehicleState::setUdpPort(int port) {
    const int clamped = qBound(1024, port, 65535);
    if (m_udpPort == clamped) return;
    m_udpPort = clamped;
    if (m_source == QLatin1String("udp")) updatePolling();
}

void VehicleState::updatePolling() {
    m_pollTimer.stop();
    m_carplayPollTimer.stop();
    m_udpSocket.close();

    if (m_source == "state") {
        m_pollTimer.start(m_pollMs);
        loadStateNow();
        // carplay status is polled inside loadStateNow() on the same timer
    } else if (m_source == "udp") {
        if (m_udpSocket.bind(QHostAddress::LocalHost, static_cast<quint16>(m_udpPort))) {
            connect(&m_udpSocket, &QUdpSocket::readyRead,
                    this, &VehicleState::onUdpDataReady, Qt::UniqueConnection);
            setConnected(false);  // becomes true on first datagram
            setLastError(QString());
        } else {
            setConnected(false);
            setLastError(QStringLiteral("Cannot bind UDP port %1").arg(m_udpPort));
        }
        if (!m_stateFile.isEmpty())
            m_carplayPollTimer.start(2000);
    } else {
        setConnected(false);
        setLastError(QString());
    }
}

void VehicleState::loadStateNow() {
    if (m_source != "state") return;

    // Poll carplay status alongside the vehicle state file (same thread slot,
    // no extra timer — avoids file I/O interrupting animations)
    loadCarplayStatusNow();

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
    const bool hasOdo = obj.contains("odo") && obj["odo"].isDouble();
    const bool hasTrip = obj.contains("trip") && obj["trip"].isDouble();
    m_externalDistanceAuthoritative = hasOdo && hasTrip;

    if (obj.contains("speed") && obj["speed"].isDouble()) {
        const double raw = obj["speed"].toDouble();
        // Adaptive low-pass filter: heavy smoothing for small integer jitter
        // (±1–3 km/h from OBD), fast tracking for real acceleration/braking.
        // alpha scales from 0.25 (diff=0) to 1.0 (diff≥12.5 km/h).
        const double diff = raw - m_speed;
        const double absDiff = diff < 0 ? -diff : diff;
        double alpha = 0.25 + absDiff * 0.06;
        if (alpha > 1.0) alpha = 1.0;
        setSpeed(m_speed + alpha * diff);
    }
    if (hasOdo) {
        setOdometer(obj["odo"].toDouble());
    }
    if (hasTrip) {
        setTrip(obj["trip"].toDouble());
    }
}

void VehicleState::integrateDistanceNow() {
    const qlonglong now = QDateTime::currentMSecsSinceEpoch();
    if (m_lastIntegrateMs <= 0) {
        m_lastIntegrateMs = now;
        return;
    }

    const qlonglong dtMs = now - m_lastIntegrateMs;
    m_lastIntegrateMs = now;
    if (dtMs <= 0) return;

    // If external state provides both odo + trip, trust those values.
    if (m_source == "state" && m_externalDistanceAuthoritative) return;

    double speedKmh = qMax(0.0, m_speed);
    if (m_profileUnit == QStringLiteral("mph")) {
        speedKmh *= 1.609344;
    }

    const double deltaKm = speedKmh * (static_cast<double>(dtMs) / 3600000.0);
    if (deltaKm <= 0.0) return;

    setOdometer(m_odometer + deltaKm);

    double newTrip = m_trip + deltaKm;
    while (newTrip >= 1000.0) newTrip -= 1000.0;
    setTrip(newTrip);
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

void VehicleState::setCarplayStatus(const QString& value) {
    if (m_carplayStatus == value) return;
    m_carplayStatus = value;
    emit carplayStatusChanged();
}

void VehicleState::loadCarplayStatusNow() {
    const QString statusPath = QFileInfo(m_stateFile).dir().filePath(
        QStringLiteral("carplay_status.json"));
    QFile file(statusPath);
    if (!file.open(QIODevice::ReadOnly)) {
        setCarplayStatus(QStringLiteral("waiting"));
        return;
    }
    QJsonParseError err;
    const auto doc = QJsonDocument::fromJson(file.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject()) return;
    const QString status = doc.object().value(QStringLiteral("status")).toString();
    if (!status.isEmpty()) setCarplayStatus(status);
}

void VehicleState::onUdpDataReady() {
    while (m_udpSocket.hasPendingDatagrams()) {
        QByteArray data;
        data.resize(static_cast<int>(m_udpSocket.pendingDatagramSize()));
        m_udpSocket.readDatagram(data.data(), data.size());

        QJsonParseError err;
        const auto doc = QJsonDocument::fromJson(data, &err);
        if (err.error != QJsonParseError::NoError || !doc.isObject()) continue;

        applyJson(doc.object());
        setConnected(true);
        setLastError(QString());
        setLastUpdateMs(QDateTime::currentMSecsSinceEpoch());
    }
}

void VehicleState::saveDistanceNow() {
    QSettings settings;
    settings.setValue(QStringLiteral("distance/odometer"), m_odometer);
    settings.setValue(QStringLiteral("distance/trip"),     m_trip);
}

void VehicleState::resetTrip() {
    if (m_externalDistanceAuthoritative && !m_stateFile.isEmpty()) {
        // Signal the VSS reader process (state or udp mode) to reset its trip counter
        const QString flagPath = QFileInfo(m_stateFile).dir().filePath(
            QStringLiteral("trip_reset.flag"));
        QFile f(flagPath);
        f.open(QIODevice::WriteOnly);
    } else {
        setTrip(0.0);
        saveDistanceNow();
    }
}
