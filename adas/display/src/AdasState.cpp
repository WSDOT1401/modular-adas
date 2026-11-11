#include "AdasState.h"

#include <QHostAddress>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QNetworkDatagram>

#include <utility>
#include <vector>

AdasState::AdasState(quint16 port, QObject* parent)
    : QObject(parent), m_port(port) {
    m_clock.start();

    if (m_port > 0) {
        if (m_socket.bind(QHostAddress::LocalHost, m_port)) {
            connect(&m_socket, &QUdpSocket::readyRead, this, &AdasState::readPending);
        } else {
            m_lastError = QStringLiteral("Cannot listen on UDP port %1: %2")
                              .arg(m_port)
                              .arg(m_socket.errorString());
            qWarning("%s", qPrintable(m_lastError));
        }
    }

    // Staleness and the sign announcement both run on time, not on data.
    m_tick.setInterval(250);
    connect(&m_tick, &QTimer::timeout, this, &AdasState::recompute);
    m_tick.start();
    recompute();
}

void AdasState::readPending() {
    while (m_socket.hasPendingDatagrams()) {
        const QNetworkDatagram dg = m_socket.receiveDatagram();
        QJsonParseError err{};
        const QJsonDocument doc = QJsonDocument::fromJson(dg.data(), &err);
        if (err.error != QJsonParseError::NoError || !doc.isObject()) {
            continue;  // not ours or malformed: drop, like every consumer does
        }
        applyJson(doc.object());
    }
}

void AdasState::applyJsonString(const QString& json) {
    const QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8());
    if (doc.isObject()) {
        applyJson(doc.object());
    }
}

void AdasState::applyJson(const QJsonObject& obj) {
    const qint64 now = m_clock.elapsed();
    bool adas = false;

    if (obj.contains(QLatin1String("speed"))) {
        m_speed = obj.value(QLatin1String("speed")).toDouble();
        m_speedAt = now;
    }
    if (obj.contains(QLatin1String("lane_warning"))) {
        m_laneWarning = obj.value(QLatin1String("lane_warning")).toBool();
        adas = true;
    }
    if (obj.contains(QLatin1String("lane_direction"))) {
        m_laneDirection = obj.value(QLatin1String("lane_direction")).toString();
        adas = true;
    }
    if (obj.contains(QLatin1String("lane_confidence"))) {
        adas = true;  // not shown, but proves the lane module is alive
    }
    if (obj.contains(QLatin1String("fcw_warning"))) {
        m_fcwWarning = obj.value(QLatin1String("fcw_warning")).toBool();
        adas = true;
    }
    if (obj.contains(QLatin1String("fcw_ttc"))) {
        m_fcwTtc = obj.value(QLatin1String("fcw_ttc")).toDouble();
        adas = true;
    }
    if (obj.contains(QLatin1String("speed_limit"))) {
        m_speedLimit = qRound(obj.value(QLatin1String("speed_limit")).toDouble());
        adas = true;
    }
    if (obj.contains(QLatin1String("sign_seen"))) {
        const QString sign = obj.value(QLatin1String("sign_seen")).toString();
        if (!sign.isEmpty()) {
            m_signSeen = sign;
            m_signAt = now;
        }
        adas = true;
    }
    if (obj.contains(QLatin1String("module_status"))) {
        const QJsonObject mods = obj.value(QLatin1String("module_status")).toObject();
        if (mods.contains(QLatin1String("lane")))
            m_moduleLane = mods.value(QLatin1String("lane")).toString();
        if (mods.contains(QLatin1String("fcw")))
            m_moduleFcw = mods.value(QLatin1String("fcw")).toString();
        if (mods.contains(QLatin1String("signs")))
            m_moduleSigns = mods.value(QLatin1String("signs")).toString();
        adas = true;
    }
    if (obj.contains(QLatin1String("system_fault"))) {
        m_systemFault = obj.value(QLatin1String("system_fault")).toString();
        adas = true;
    }
    if (adas) {
        m_adasAt = now;
    }

    recompute();

    // Control events last, so the UI reacts to the state they arrived with.
    if (obj.contains(QLatin1String("input"))) {
        emit inputEvent(obj.value(QLatin1String("input")).toString());
    }
}

QString AdasState::moduleState(const QString& raw) const {
    // No data: whatever the driver chose, nothing works right now.
    if (!m_adasOnline) {
        return QStringLiteral("paused");
    }
    if (raw == QLatin1String("on") || raw == QLatin1String("paused")) {
        return raw;
    }
    return QStringLiteral("off");
}

void AdasState::acknowledge() {
    if (m_level == QLatin1String("caution") || m_level == QLatin1String("info")) {
        m_ackReason = m_reason;
        recompute();
    }
}

void AdasState::recompute() {
    const qint64 now = m_clock.elapsed();

    m_adasOnline = m_adasAt >= 0 && now - m_adasAt < kAdasStaleMs;
    m_hasSpeed = m_speedAt >= 0 && now - m_speedAt < kSpeedStaleMs;
    m_signFresh = !m_signSeen.isEmpty() && m_signAt >= 0 && now - m_signAt < kSignShowMs;
    m_overspeed = m_hasSpeed && m_speedLimit > 0 && m_speed > m_speedLimit + kOverspeedMargin;

    // Every alert that is true right now, highest priority first.
    std::vector<std::pair<QString, QString>> active;  // (level, reason)
    if (m_adasOnline && m_fcwWarning)
        active.emplace_back(QStringLiteral("warning"), QStringLiteral("fcw"));
    if (!m_adasOnline)
        active.emplace_back(QStringLiteral("system"), QStringLiteral("adas_offline"));
    if (m_adasOnline && !m_systemFault.isEmpty())
        active.emplace_back(QStringLiteral("system"), QStringLiteral("fault"));
    if (m_adasOnline && m_laneWarning)
        active.emplace_back(QStringLiteral("caution"),
                            m_laneDirection == QLatin1String("right")
                                ? QStringLiteral("lane_right")
                                : QStringLiteral("lane_left"));
    if (m_overspeed)
        active.emplace_back(QStringLiteral("caution"), QStringLiteral("overspeed"));
    if (m_signFresh)
        active.emplace_back(QStringLiteral("info"), QStringLiteral("sign"));

    // An acknowledgement lasts until its alert clears.
    bool ackStillActive = false;
    for (const auto& a : active) {
        if (a.second == m_ackReason) ackStillActive = true;
    }
    if (!ackStillActive) m_ackReason.clear();

    m_level = QStringLiteral("none");
    m_reason = QStringLiteral("none");
    for (const auto& a : active) {
        const bool hideable = a.first == QLatin1String("caution") || a.first == QLatin1String("info");
        if (hideable && a.second == m_ackReason) continue;
        m_level = a.first;
        m_reason = a.second;
        break;
    }

    emit changed();
}
