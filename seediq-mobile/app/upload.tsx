import React, { useState } from "react";
import { Text, View, StyleSheet } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { ApiError, NetworkError, api } from "@/lib/api";
import { AiScreenShell, ResultHeading } from "@/components/ai-screen";
import { Card, Button, Badge } from "@/components/ui";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";

interface UploadResult {
  status: string;
  message?: string;
  filename?: string;
  detected_type?: string;
  version?: string;
  rows?: number;
  columns?: number;
  original_storage_path?: string;
  processed_storage_path?: string;
}

const MAX_SIZE = 10 * 1024 * 1024; // 10 MB — matches backend limit

export default function UploadScreen() {
  const { t } = useI18n();
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileUri, setFileUri] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  const pickDocument = async () => {
    setError(null);
    setResult(null);
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: "text/comma-separated-values,text/csv,text/plain",
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets || res.assets.length === 0) return;
      const asset = res.assets[0];
      if (asset.size && asset.size > MAX_SIZE) {
        setError(t("upload.errSize"));
        return;
      }
      setFileName(asset.name);
      setFileUri(asset.uri);
      setFileSize(asset.size ?? null);
    } catch {
      setError(t("upload.errPicker"));
    }
  };

  const handleUpload = async () => {
    if (!fileUri || !fileName) {
      setError(t("upload.errSelectFirst"));
      return;
    }
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      // React Native FormData file shape
      formData.append("file", {
        uri: fileUri,
        name: fileName,
        type: "text/csv",
      } as any);

      const res = await api<UploadResult>("/api/datasets/upload", { method: "POST", formData });
      setResult(res);
    } catch (e) {
      setError(
        e instanceof ApiError || e instanceof NetworkError ? e.message : t("upload.errUpload"),
      );
    } finally {
      setUploading(false);
    }
  };

  const reset = () => {
    setFileName(null);
    setFileUri(null);
    setFileSize(null);
    setResult(null);
    setError(null);
  };

  return (
    <AiScreenShell
      title={t("upload.title")}
      subtitle={t("upload.subtitle")}
      isPredicting={uploading}
      onPredict={handleUpload}
      onRetry={handleUpload}
      error={error}
      result={
        result ? (
          <View style={{ gap: theme.spacing.md }}>
            <ResultHeading>{t("upload.resultHeading")}</ResultHeading>
            <Card>
              <Text style={styles.cardTitle}>{result.filename}</Text>
              {result.detected_type ? (
                <Badge label={t("upload.detected", { type: result.detected_type })} tone="info" small />
              ) : null}
              <Text style={styles.meta}>{result.message}</Text>
              {result.rows !== undefined && (
                <Text style={styles.meta}>
                  {t("upload.rowsColumns", {
                    rows: result.rows.toLocaleString(),
                    columns: result.columns,
                    version: result.version,
                  })}
                </Text>
              )}
            </Card>
            <Button label={t("upload.uploadAnother")} variant="outline" onPress={reset} />
          </View>
        ) : null
      }
      predictLabel={t("upload.predict")}
    >
      <Card
        style={{
          borderStyle: "dashed",
          borderWidth: 1.5,
          borderColor: fileName ? theme.colors.primaryBorder : theme.colors.borderStrong,
          alignItems: "center",
          padding: theme.spacing.xl,
        }}
      >
        <Text style={styles.pickTitle}>{fileName || t("upload.selectCsv")}</Text>
        <Text style={styles.pickMeta}>
          {fileSize
            ? `${(fileSize / (1024 * 1024)).toFixed(2)} MB`
            : t("upload.onlyCsv")}
        </Text>
        <Button
          label={t("upload.browse")}
          variant="outline"
          onPress={pickDocument}
          style={{ marginTop: theme.spacing.md }}
        />
      </Card>
    </AiScreenShell>
  );
}

const styles = StyleSheet.create({
  pickTitle: { fontSize: 15, fontWeight: "600", color: theme.colors.text, textAlign: "center" as const },
  pickMeta: { fontSize: 12, color: theme.colors.textMuted, marginTop: 4 },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 6 },
  meta: { fontSize: 12, color: theme.colors.textMuted, marginTop: 6, lineHeight: 18 },
});
