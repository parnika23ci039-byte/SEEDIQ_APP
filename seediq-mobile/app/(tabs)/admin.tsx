import React, { useState } from "react";
import { Text, View, StyleSheet } from "react-native";
import { Users, ScrollText, Play, Trash2, ChevronDown, ChevronUp } from "lucide-react-native";
import { Screen, Card, Row, Badge, Button, SectionTitle, Loading, ErrorBanner, EmptyState } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { api, ApiError, NetworkError } from "@/lib/api";
import { theme } from "@/theme/theme";
import type {
  AdminUsersResponse,
  ActivityLogsResponse,
  RetrainResponse,
  RetrainReport,
  RetrainModelReport,
} from "@/lib/types";

/** Held-out headline for a model row: classification -> accuracy %, regression -> R². */
function formatTest(model: RetrainModelReport, t: ReturnType<typeof useI18n>["t"]): string {
  const test = model.test as Record<string, number> | null | undefined;
  if (!test) return t("admin.retrainMetricsUnavailable");
  if (typeof test.accuracy === "number") return `${(test.accuracy * 100).toFixed(2)}%`;
  if (typeof test.r2 === "number") return `R² ${test.r2.toFixed(4)}`;
  return t("admin.retrainMetricsUnavailable");
}

/**
 * Structured result of the last retraining run, rendered from the JSON report
 * the pipeline writes (`reports/retrain_report.json`), not from parsing stdout.
 * Each row shows the held-out test number and the train/test generalization gap.
 */
function RetrainSummary({ report, rawLog }: { report: RetrainReport; rawLog: string | null }) {
  const { t } = useI18n();
  const [logOpen, setLogOpen] = useState(false);
  const gen = report.generalization;
  const genTone =
    gen?.status === "good" ? "success" : gen?.status === "moderate" ? "warning" : "danger";

  return (
    <View style={{ gap: theme.spacing.md }}>
      <Card>
        <Text style={styles.cardTitle}>{t("admin.retrainSummary")}</Text>
        <Row
          label={t("admin.retrainRun")}
          value={`${report.run_id} · ${report.timestamp}`}
        />
        <Row
          label={t("admin.retrainDuration")}
          value={`${report.duration_seconds ?? "—"} s`}
        />
        {gen ? (
          <Row
            label={t("admin.retrainGeneralization")}
            value={gen.status.toUpperCase()}
            tone={genTone}
          />
        ) : null}
        <Row
          label={t("admin.retrainEntries")}
          value={String(report.registry_entries_added ?? "—")}
        />
        {report.success === false && report.error ? (
          <Text style={styles.reportError}>{report.error}</Text>
        ) : null}
      </Card>

      {report.datasets.length > 0 ? (
        <Card>
          <Text style={styles.cardTitle}>{t("admin.retrainDatasets")}</Text>
          {report.datasets.map((d) => (
            <Row
              key={d.domain}
              label={`${d.domain} · ${t("admin.retrainRecords", { count: d.records })}`}
              value={d.synthetic ? t("admin.retrainSynthetic") : (d.path ?? "")}
              tone={d.synthetic ? "warning" : "default"}
            />
          ))}
        </Card>
      ) : null}

      {report.models.length > 0 ? (
        <Card>
          <Text style={styles.cardTitle}>{t("admin.modelRetraining")}</Text>
          {report.models.map((m, i) => {
            const gapTone =
              m.gap_status === "good" ? "success" : m.gap_status === "moderate" ? "warning" : "danger";
            return (
              <View key={`${m.artifact}-${i}`} style={styles.modelRow}>
                <View style={styles.modelTop}>
                  <Text style={styles.modelName} numberOfLines={2}>
                    {m.name}
                  </Text>
                  <Badge
                    label={`${(Math.abs(m.gap ?? 0) * 100).toFixed(1)} pp`}
                    tone={gapTone}
                    small
                  />
                </View>
                <View style={styles.modelBadges}>
                  <Badge label={`${t("admin.retrainTestColumn")}: ${formatTest(m, t)}`} tone="primary" small />
                  <Badge label={m.artifact.split("/").pop() ?? m.artifact} tone="neutral" small />
                  {m.dataset_provenance === "synthetic-generated" ? (
                    <Badge label={t("admin.retrainSynthetic")} tone="warning" small />
                  ) : null}
                  {m.simulated_quantum ? (
                    <Badge label={t("admin.retrainQuantumSimulated")} tone="info" small />
                  ) : null}
                </View>
              </View>
            );
          })}
        </Card>
      ) : null}

      {rawLog ? (
        <Card>
          <Button
            label={logOpen ? t("admin.retrainHideLog") : t("admin.retrainShowLog")}
            variant="ghost"
            icon={
              logOpen ? (
                <ChevronUp size={16} color={theme.colors.primary} />
              ) : (
                <ChevronDown size={16} color={theme.colors.primary} />
              )
            }
            onPress={() => setLogOpen((v) => !v)}
          />
          {logOpen ? (
            <View style={styles.console}>
              <Text style={styles.consoleText}>{rawLog.slice(-4000)}</Text>
            </View>
          ) : null}
        </Card>
      ) : null}
    </View>
  );
}

export default function AdminScreen() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "Admin";

  const [users, setUsers] = useState<AdminUsersResponse | null>(null);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState<string | null>(null);

  const [logs, setLogs] = useState<ActivityLogsResponse | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);

  const [retraining, setRetraining] = useState(false);
  const [retrainOutput, setRetrainOutput] = useState<string | null>(null);
  const [retrainReport, setRetrainReport] = useState<RetrainReport | null>(null);
  const [showRawLog, setShowRawLog] = useState(false);
  const [retrainError, setRetrainError] = useState<string | null>(null);

  // Activity-log data cleanup. Two-step so a stray tap cannot delete records.
  const [purgeArmed, setPurgeArmed] = useState(false);
  const [purging, setPurging] = useState(false);
  const [purgeMessage, setPurgeMessage] = useState<string | null>(null);
  const [purgeError, setPurgeError] = useState<string | null>(null);

  const purgeLogs = async () => {
    if (!purgeArmed) {
      setPurgeArmed(true);
      setPurgeMessage(null);
      setPurgeError(null);
      return;
    }
    setPurging(true);
    setPurgeError(null);
    setPurgeMessage(null);
    try {
      const res = await api<{ status: string; message?: string; deleted?: Record<string, number>; remaining?: number }>(
        "/api/admin/activity-logs/purge",
        {
          method: "POST",
          timeoutMs: 60000,
          body: { confirm: "PURGE_ACTIVITY_LOGS" },
        },
      );
      const removed = (res.deleted?.sqlite_deleted ?? 0) + (res.deleted?.supabase_deleted ?? 0);
      setPurgeMessage(
        `${t("adminData.purgeDone", { count: removed })} ${
          res.remaining !== undefined ? t("adminData.purgeRemaining", { count: res.remaining }) : ""
        }`,
      );
      setPurgeArmed(false);
      await loadLogs();
    } catch (e) {
      setPurgeError(
        e instanceof ApiError || e instanceof NetworkError ? e.message : t("adminData.purgeFailed"),
      );
    } finally {
      setPurging(false);
    }
  };

  const loadUsers = async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      setUsers(await api<AdminUsersResponse>("/api/admin/users"));
    } catch (e) {
      setUsersError(
        e instanceof ApiError || e instanceof NetworkError ? e.message : t("admin.errUsers"),
      );
    } finally {
      setUsersLoading(false);
    }
  };

  const loadLogs = async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      setLogs(await api<ActivityLogsResponse>("/api/admin/activity-logs?limit=50"));
    } catch (e) {
      setLogsError(
        e instanceof ApiError || e instanceof NetworkError ? e.message : t("admin.errLogs"),
      );
    } finally {
      setLogsLoading(false);
    }
  };

  const triggerRetrain = async () => {
    setRetraining(true);
    setRetrainError(null);
    setRetrainOutput(null);
    setRetrainReport(null);
    setShowRawLog(false);
    try {
      const res = await api<RetrainResponse>("/api/retrain", { method: "POST", timeoutMs: 300000 });
      if (res.status === "success") {
        setRetrainReport(res.report ?? null);
        setRetrainOutput(res.output ?? null);
        if (!res.report) setRetrainError(t("admin.retrainNoReport"));
      } else {
        setRetrainError(res.message || res.error?.slice(-500) || t("admin.retrainFailed"));
        if (res.report) setRetrainReport(res.report);
        if (res.output) setRetrainOutput(res.output);
      }
    } catch (e) {
      setRetrainError(
        e instanceof ApiError || e instanceof NetworkError
          ? e.message
          : t("admin.retrainRequestFailed"),
      );
    } finally {
      setRetraining(false);
    }
  };

  return (
    <Screen>
      <SectionTitle>{t("admin.title")}</SectionTitle>
      <Text style={styles.intro}>
        {t("admin.intro", {
          role: user?.role ?? "",
          scope: isAdmin ? t("admin.fullPrivileges") : t("admin.researcherScope"),
        })}
      </Text>

      {/* Users */}
      <SectionTitle>{t("admin.users")}</SectionTitle>
      {!users && !usersLoading ? (
        <Button
          label={t("admin.loadUsers")}
          variant="outline"
          icon={<Users size={16} color={theme.colors.primary} />}
          onPress={loadUsers}
        />
      ) : null}
      {usersLoading && <Loading label={t("admin.loadingUsers")} />}
      {usersError && <ErrorBanner message={usersError} onRetry={loadUsers} />}
      {users && (
        <Card>
          <Text style={styles.cardTitle}>
            {t("admin.registeredUsers", { count: users.total_users })}
          </Text>
          {users.users.slice(0, 30).map((u, i) => (
            <Row
              key={`${u.id}-${i}`}
              label={`${u.display_name} (${u.email})`}
              value={<Badge label={u.role} tone={u.role === "Admin" ? "primary" : u.role === "Researcher" ? "info" : "neutral"} small />}
            />
          ))}
          {users.users.length > 30 && (
            <Text style={styles.moreText}>
              {t("admin.more", { count: users.users.length - 30 })}
            </Text>
          )}
        </Card>
      )}

      {/* Activity logs */}
      <SectionTitle>{t("admin.activityLogs")}</SectionTitle>
      {!logs && !logsLoading ? (
        <Button
          label={t("admin.loadLogs")}
          variant="outline"
          icon={<ScrollText size={16} color={theme.colors.primary} />}
          onPress={loadLogs}
        />
      ) : null}
      {logsLoading && <Loading label={t("admin.loadingLogs")} />}
      {logsError && <ErrorBanner message={logsError} onRetry={loadLogs} />}
      {logs && (logs.logs.length === 0 ? (
        <EmptyState title={t("admin.noActivityTitle")} message={t("admin.noActivityMessage")} />
      ) : (
        <Card>
          <Text style={styles.cardTitle}>
            {t("admin.recentEvents", { count: logs.count })}
          </Text>
          {logs.logs.slice(0, 30).map((l) => (
            <View key={l.id} style={styles.logRow}>
              <View style={styles.logTop}>
                <Badge label={l.event_type} tone={l.status === "FAILED" ? "danger" : "success"} small />
                <Text style={styles.logTime}>{new Date(l.created_at).toLocaleString()}</Text>
              </View>
              <Text style={styles.logDetails} numberOfLines={2}>
                {JSON.stringify(l.details)}
              </Text>
            </View>
          ))}
        </Card>
      ))}

      {/* Activity-log data cleanup (Admin only).
          This DELETES the stored records — it does not hide the screen — and the
          logger keeps recording later events as before. */}
      {isAdmin ? (
        <Card>
          <Text style={styles.cardTitle}>{t("adminData.purgeLogs")}</Text>
          <Text style={styles.retrainDesc}>{t("adminData.purgeDesc")}</Text>
          <Button
            label={purgeArmed ? t("adminData.purgeConfirm") : t("adminData.purgeLogs")}
            variant={purgeArmed ? "danger" : "outline"}
            icon={<Trash2 size={16} color={purgeArmed ? theme.colors.textInverse : theme.colors.danger} />}
            onPress={purgeLogs}
            loading={purging}
          />
          {purgeArmed && !purging ? (
            <Button
              label={t("adminData.purgeCancel")}
              variant="ghost"
              onPress={() => setPurgeArmed(false)}
            />
          ) : null}
          {purgeMessage && <Text style={styles.purgeOk}>{purgeMessage}</Text>}
          {purgeError && <ErrorBanner message={purgeError} onRetry={purgeLogs} />}
        </Card>
      ) : (
        <Card>
          <Text style={styles.lockText}>{t("adminData.purgeLocked")}</Text>
        </Card>
      )}

      {/* Retraining (Admin only) */}
      <SectionTitle>{t("admin.modelRetraining")}</SectionTitle>
      {isAdmin ? (
        <Card>
          <Text style={styles.cardTitle}>{t("admin.retrainTitle")}</Text>
          <Text style={styles.retrainDesc}>{t("admin.retrainDesc")}</Text>
          <Button
            label={t("admin.startRetraining")}
            icon={<Play size={16} color="#fff" />}
            onPress={triggerRetrain}
            loading={retraining}
          />
          {retrainReport && <RetrainSummary report={retrainReport} rawLog={retrainOutput} />}
          {retrainOutput && !retrainReport && (
            <View style={styles.console}>
              <Text style={styles.consoleText}>{retrainOutput}</Text>
            </View>
          )}
          {retrainError && <ErrorBanner message={retrainError} onRetry={triggerRetrain} />}
        </Card>
      ) : (
        <Card>
          <Text style={styles.lockText}>{t("admin.retrainLocked")}</Text>
        </Card>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19, marginTop: -4 },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 4 },
  moreText: { fontSize: 12, color: theme.colors.textMuted, marginTop: 4 },
  logRow: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: theme.colors.border, gap: 4 },
  logTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  logTime: { fontSize: 10, color: theme.colors.textMuted },
  logDetails: { fontSize: 11, color: theme.colors.textSecondary, fontFamily: undefined },
  retrainDesc: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19, marginBottom: 8 },
  console: {
    backgroundColor: theme.colors.navBackground,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    marginTop: theme.spacing.md,
  },
  consoleText: { color: theme.colors.sage, fontSize: 11, lineHeight: 16 },
  modelRow: {
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    gap: 6,
  },
  modelTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 },
  modelName: { fontSize: 13, fontWeight: "700", color: theme.colors.text, flex: 1 },
  modelBadges: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  reportError: { fontSize: 12, color: theme.colors.danger, marginTop: 6, lineHeight: 17 },
  lockText: { fontSize: 13, color: theme.colors.textMuted, lineHeight: 19 },
  purgeOk: { fontSize: 12, color: theme.colors.success, marginTop: 6, lineHeight: 17 },
});
