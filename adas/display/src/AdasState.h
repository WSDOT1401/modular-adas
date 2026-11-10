#pragma once

#include <QElapsedTimer>
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QUdpSocket>

// Everything the ADAS display shows, fed by UDP JSON datagrams that follow
// adas/protocol (keys.py / vehicle_state.schema.json).
//
// Producers report facts (a lane drift, a sign, a speed); this class decides
// which one the driver sees: `level` + `reason` are the single answer both
// layouts render. Priority, highest first:
//   fcw (warning) > adas offline (system) > fault (system)
//   > lane drift (caution) > over the limit (caution) > new sign (info)
// A press on the encoder acknowledges a caution or info alert: it stays
// hidden until that alert clears. Warnings and system alerts cannot be hidden.
class AdasState : public QObject {
    Q_OBJECT
    Q_PROPERTY(double speed READ speed NOTIFY changed)
    Q_PROPERTY(bool hasSpeed READ hasSpeed NOTIFY changed)
    Q_PROPERTY(int speedLimit READ speedLimit NOTIFY changed)
    Q_PROPERTY(bool overspeed READ overspeed NOTIFY changed)
    Q_PROPERTY(bool laneWarning READ laneWarning NOTIFY changed)
    Q_PROPERTY(QString laneDirection READ laneDirection NOTIFY changed)
    Q_PROPERTY(bool fcwWarning READ fcwWarning NOTIFY changed)
    Q_PROPERTY(double fcwTtc READ fcwTtc NOTIFY changed)
    Q_PROPERTY(QString signSeen READ signSeen NOTIFY changed)
    Q_PROPERTY(bool signFresh READ signFresh NOTIFY changed)
    Q_PROPERTY(QString moduleLane READ moduleLane NOTIFY changed)
    Q_PROPERTY(QString moduleFcw READ moduleFcw NOTIFY changed)
    Q_PROPERTY(QString moduleSigns READ moduleSigns NOTIFY changed)
    Q_PROPERTY(QString systemFault READ systemFault NOTIFY changed)
    Q_PROPERTY(bool adasOnline READ adasOnline NOTIFY changed)
    Q_PROPERTY(QString level READ level NOTIFY changed)
    Q_PROPERTY(QString reason READ reason NOTIFY changed)
    Q_PROPERTY(int udpPort READ udpPort CONSTANT)
    Q_PROPERTY(QString lastError READ lastError NOTIFY changed)

public:
    // How long data stays valid without a fresh datagram.
    static constexpr qint64 kSpeedStaleMs = 3000;
    static constexpr qint64 kAdasStaleMs = 3000;
    // How long a newly read sign is announced.
    static constexpr qint64 kSignShowMs = 8000;
    // km/h above the limit before "over the limit" shows.
    static constexpr double kOverspeedMargin = 2.0;

    explicit AdasState(quint16 port, QObject* parent = nullptr);

    double speed() const { return m_speed; }
    bool hasSpeed() const { return m_hasSpeed; }
    int speedLimit() const { return m_speedLimit; }
    bool overspeed() const { return m_overspeed; }
    bool laneWarning() const { return m_laneWarning && m_adasOnline; }
    QString laneDirection() const { return m_laneDirection; }
    bool fcwWarning() const { return m_fcwWarning && m_adasOnline; }
    double fcwTtc() const { return m_fcwTtc; }
    QString signSeen() const { return m_signSeen; }
    bool signFresh() const { return m_signFresh; }
    QString moduleLane() const { return moduleState(m_moduleLane); }
    QString moduleFcw() const { return moduleState(m_moduleFcw); }
    QString moduleSigns() const { return moduleState(m_moduleSigns); }
    QString systemFault() const { return m_systemFault; }
    bool adasOnline() const { return m_adasOnline; }
    QString level() const { return m_level; }
    QString reason() const { return m_reason; }
    int udpPort() const { return m_port; }
    QString lastError() const { return m_lastError; }

    // Feed one datagram's worth of JSON (used by the UDP socket, by demo mode
    // and by --scenario).
    Q_INVOKABLE void applyJsonString(const QString& json);
    // Hide the current caution/info alert until it clears.
    Q_INVOKABLE void acknowledge();

    void applyJson(const QJsonObject& obj);

signals:
    void changed();
    // A driver control event: rotate_cw, rotate_ccw, press, long_press.
    void inputEvent(const QString& name);

private:
    void readPending();
    void recompute();
    QString moduleState(const QString& raw) const;

    QUdpSocket m_socket;
    QTimer m_tick;
    QElapsedTimer m_clock;
    quint16 m_port;
    QString m_lastError;

    double m_speed = 0.0;
    qint64 m_speedAt = -1;
    int m_speedLimit = 0;
    bool m_laneWarning = false;
    QString m_laneDirection = QStringLiteral("none");
    bool m_fcwWarning = false;
    double m_fcwTtc = 0.0;
    QString m_signSeen;
    qint64 m_signAt = -1;
    QString m_moduleLane;
    QString m_moduleFcw;
    QString m_moduleSigns;
    QString m_systemFault;
    qint64 m_adasAt = -1;

    // Derived in recompute().
    bool m_hasSpeed = false;
    bool m_overspeed = false;
    bool m_signFresh = false;
    bool m_adasOnline = false;
    QString m_level = QStringLiteral("none");
    QString m_reason = QStringLiteral("none");
    QString m_ackReason;
};
