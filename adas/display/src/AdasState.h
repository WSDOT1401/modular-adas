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
//
// The driver can switch each feature off from the menu. The choice is saved,
// hides that feature's alerts here at once, and is sent to the vision service
// (feature_enable, on the control port) so it stops running the stage.
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
    Q_PROPERTY(bool leadVehicle READ leadVehicle NOTIFY changed)
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
    // The driver's choices from the menu (saved between runs).
    Q_PROPERTY(bool laneEnabled READ laneEnabled NOTIFY changed)
    Q_PROPERTY(bool fcwEnabled READ fcwEnabled NOTIFY changed)
    Q_PROPERTY(bool signsEnabled READ signsEnabled NOTIFY changed)

public:
    // How long data stays valid without a fresh datagram.
    static constexpr qint64 kSpeedStaleMs = 3000;
    static constexpr qint64 kAdasStaleMs = 3000;
    // How long a newly read sign is announced.
    static constexpr qint64 kSignShowMs = 8000;
    // km/h above the limit before "over the limit" shows.
    static constexpr double kOverspeedMargin = 2.0;

    // How often the driver's choices are re-sent, so a restarted vision
    // service catches up.
    static constexpr int kFeatureResendMs = 1000;

    // controlPort 0: don't send the driver's choices anywhere.
    explicit AdasState(quint16 port, quint16 controlPort = 9102, QObject* parent = nullptr);

    double speed() const { return m_speed; }
    bool hasSpeed() const { return m_hasSpeed; }
    int speedLimit() const { return m_signsOn ? m_speedLimit : 0; }
    bool overspeed() const { return m_overspeed; }
    bool laneWarning() const { return m_laneWarning && m_adasOnline && m_laneOn; }
    QString laneDirection() const { return m_laneDirection; }
    bool fcwWarning() const { return m_fcwWarning && m_adasOnline && m_fcwOn; }
    double fcwTtc() const { return m_fcwTtc; }
    bool leadVehicle() const { return m_leadVehicle && m_adasOnline && m_fcwOn; }
    QString signSeen() const { return m_signSeen; }
    bool signFresh() const { return m_signFresh; }
    QString moduleLane() const { return moduleState(m_moduleLane, m_laneOn); }
    QString moduleFcw() const { return moduleState(m_moduleFcw, m_fcwOn); }
    QString moduleSigns() const { return moduleState(m_moduleSigns, m_signsOn); }
    QString systemFault() const { return m_systemFault; }
    bool adasOnline() const { return m_adasOnline; }
    QString level() const { return m_level; }
    QString reason() const { return m_reason; }
    int udpPort() const { return m_port; }
    QString lastError() const { return m_lastError; }
    bool laneEnabled() const { return m_laneOn; }
    bool fcwEnabled() const { return m_fcwOn; }
    bool signsEnabled() const { return m_signsOn; }

    // Feed one datagram's worth of JSON (used by the UDP socket, by demo mode
    // and by --scenario).
    Q_INVOKABLE void applyJsonString(const QString& json);
    // Hide the current caution/info alert until it clears.
    Q_INVOKABLE void acknowledge();
    // Switch a feature on/off: "lane", "fcw" or "signs".
    Q_INVOKABLE void toggleFeature(const QString& name);

    void applyJson(const QJsonObject& obj);
    // Take only driver input ("input") from the network, no data: for
    // --scenario, where the scenario supplies the data.
    void setInputOnly(bool on) { m_inputOnly = on; }

signals:
    void changed();
    // A driver control event: rotate_cw, rotate_ccw, press, long_press.
    void inputEvent(const QString& name);

private:
    void readPending();
    void recompute();
    QString moduleState(const QString& raw, bool enabled) const;
    void sendFeatures();

    QUdpSocket m_socket;
    QUdpSocket m_controlSocket;
    QTimer m_controlTick;
    quint16 m_controlPort;
    QTimer m_tick;
    QElapsedTimer m_clock;
    quint16 m_port;
    QString m_lastError;
    bool m_inputOnly = false;

    double m_speed = 0.0;
    qint64 m_speedAt = -1;
    int m_speedLimit = 0;
    bool m_laneWarning = false;
    QString m_laneDirection = QStringLiteral("none");
    bool m_fcwWarning = false;
    double m_fcwTtc = 0.0;
    bool m_leadVehicle = false;
    QString m_signSeen;
    qint64 m_signAt = -1;
    QString m_moduleLane;
    QString m_moduleFcw;
    QString m_moduleSigns;
    QString m_systemFault;
    qint64 m_adasAt = -1;

    // The driver's choices.
    bool m_laneOn = true;
    bool m_fcwOn = true;
    bool m_signsOn = true;

    // Derived in recompute().
    bool m_hasSpeed = false;
    bool m_overspeed = false;
    bool m_signFresh = false;
    bool m_adasOnline = false;
    QString m_level = QStringLiteral("none");
    QString m_reason = QStringLiteral("none");
    QString m_ackReason;
};
