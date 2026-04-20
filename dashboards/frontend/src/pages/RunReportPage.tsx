import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import DownloadIcon from "@mui/icons-material/Download";
import { useExportReport, useReportById, useRunReport } from "@/api";

export default function RunReportPage() {
  const [searchParams] = useSearchParams();
  const reportId = searchParams.get("reportId");

  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<{
    reportId: string;
    columns: string[];
    rows: Array<Record<string, unknown>>;
    rowCount: number;
    executedAt: string;
  } | null>(null);
  const [reportAsOf, setReportAsOf] = useState<string>(() => new Date().toISOString());
  const autoRunRef = useRef<string | null>(null);

  const { data: report, isLoading } = useReportById(reportId);
  const runReport = useRunReport();
  const exportReport = useExportReport();

  useEffect(() => {
    if (!report) {
      setVariableValues({});
      return;
    }

    setVariableValues((prev) => {
      const next: Record<string, string> = {};
      for (const variableName of report.variables) {
        next[variableName] = prev[variableName] ?? "";
      }
      return next;
    });
  }, [report]);

  const requiredVarsFilled = useMemo(() => {
    if (!report) return false;
    return report.variables.every((v) => (variableValues[v] ?? "").trim().length > 0);
  }, [report, variableValues]);

  const handleRun = () => {
    if (!report) return;
    if (report.variables.length > 0 && !requiredVarsFilled) return;

    runReport.mutate(
      {
        reportId: report.id,
        variables: report.variables.reduce<Record<string, string>>((acc, variableName) => {
          acc[variableName] = (variableValues[variableName] ?? "").trim();
          return acc;
        }, {}),
      },
      {
        onSuccess: (result) => {
          setRunResult(result);
          setReportAsOf(new Date().toISOString());
          setError(null);
        },
        onError: (err) => setError(err.message),
      },
    );
  };

  const handleExport = () => {
    if (!report) return;
    if (report.variables.length > 0 && !requiredVarsFilled) return;

    exportReport.mutate(
      {
        reportId: report.id,
        variables: report.variables.reduce<Record<string, string>>((acc, variableName) => {
          acc[variableName] = (variableValues[variableName] ?? "").trim();
          return acc;
        }, {}),
        fileName: `${report.name}.xlsx`,
        asOf: reportAsOf,
      },
      {
        onError: (err) => setError(err.message),
      },
    );
  };

  useEffect(() => {
    if (!report) return;
    if (report.variables.length > 0) {
      autoRunRef.current = null;
      return;
    }

    if (autoRunRef.current === report.id) {
      return;
    }

    autoRunRef.current = report.id;
    runReport.mutate(
      { reportId: report.id, variables: {} },
      {
        onSuccess: (result) => {
          setRunResult(result);
          setReportAsOf(new Date().toISOString());
          setError(null);
        },
        onError: (err) => setError(err.message),
      },
    );
  }, [report, runReport]);

  const runLabel = runResult ? "Refresh" : "Run";
  const runIcon = runResult ? <RefreshIcon /> : <PlayArrowIcon />;

  if (!reportId) {
    return (
      <Box sx={{ px: 3, py: 4 }}>
        <Alert severity="warning">Missing reportId in URL.</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ px: 3, py: 3, height: "100%", display: "flex", flexDirection: "column", gap: 2 }}>
      {error && <Alert severity="error">{error}</Alert>}

      {isLoading || !report ? (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Stack spacing={2} sx={{ minHeight: 0, flex: 1 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems={{ xs: "stretch", lg: "flex-start" }}>
              <Box sx={{ minWidth: 0, width: { xs: "100%", lg: 300 }, flexShrink: 0 }}>
                <Typography variant="h5" fontWeight={700} noWrap>
                  {report.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Records: {runResult ? runResult.rowCount : "-"} | As on {new Date(reportAsOf).toLocaleString("en-IN")}
                </Typography>
              </Box>

              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "flex-start" }}>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ flexWrap: "wrap", flex: 1, minWidth: 0 }}>
                    {report.variables.map((variableName) => (
                      <TextField
                        key={variableName}
                        label={variableName}
                        value={variableValues[variableName] ?? ""}
                        onChange={(e) =>
                          setVariableValues((prev) => ({
                            ...prev,
                            [variableName]: e.target.value,
                          }))
                        }
                        size="small"
                        sx={{ minWidth: 160 }}
                      />
                    ))}
                    {report.variables.length === 0 && <Box sx={{ flex: 1 }} />}
                  </Stack>

                  <Stack direction="row" spacing={1} sx={{ flexShrink: 0, alignSelf: { xs: "stretch", md: "auto" } }}>
                  <Button
                    variant="contained"
                    startIcon={runReport.isPending ? <CircularProgress size={16} color="inherit" /> : runIcon}
                    onClick={handleRun}
                    disabled={runReport.isPending || (report.variables.length > 0 && !requiredVarsFilled)}
                  >
                    {runLabel}
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={
                      exportReport.isPending ? <CircularProgress size={16} color="inherit" /> : <DownloadIcon />
                    }
                    onClick={handleExport}
                    disabled={
                      exportReport.isPending ||
                      runReport.isPending ||
                      (report.variables.length > 0 && !requiredVarsFilled)
                    }
                  >
                    Export Excel
                  </Button>
                </Stack>
                </Stack>
              </Box>
            </Stack>
          </Paper>

          <Divider />

          <Paper variant="outlined" sx={{ flex: 1, minHeight: 240, overflow: "hidden" }}>
            {runResult ? (
              <>
                <TableContainer sx={{ maxHeight: "100%" }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        {runResult.columns.map((col) => (
                          <TableCell key={col}>{col}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {runResult.rows.map((row, index) => (
                        <TableRow key={index} hover>
                          {runResult.columns.map((col) => (
                            <TableCell key={`${index}-${col}`}>
                              {row[col] === null || row[col] === undefined ? "" : String(row[col])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                {runResult.rows.length === 0 && (
                  <Box sx={{ p: 2 }}>
                    <Typography variant="body2" color="text.secondary">
                      No results found for the current inputs.
                    </Typography>
                  </Box>
                )}
              </>
            ) : (
              <Box sx={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  {report.variables.length > 0
                    ? "Set inputs and click Run to view results."
                    : "Loading results..."}
                </Typography>
              </Box>
            )}
          </Paper>
        </Stack>
      )}
    </Box>
  );
}
