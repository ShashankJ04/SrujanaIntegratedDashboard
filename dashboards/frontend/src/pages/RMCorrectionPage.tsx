import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import EditNoteIcon from "@mui/icons-material/EditNote";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import { useRMCorrectionBatchDetails, useRMCorrectionEntries } from "@/api";
import type { RMCorrectionEntry } from "@/api";

type Severity = "success" | "error";

type CorrectionForm = {
  rmCorrection: string;
  rmRemarks: string;
  scrapCorrection: string;
  scrapRemarks: string;
};

type FormState = Record<string, CorrectionForm>;
const PAGE_SIZE = 30;
const EMPTY_FORM: CorrectionForm = {
  rmCorrection: "",
  rmRemarks: "",
  scrapCorrection: "",
  scrapRemarks: "",
};

function rowKey(entry: RMCorrectionEntry): string {
  return `${entry.rawMaterial}__${entry.batch}`;
}

function isEntered(value: string): boolean {
  return value.trim() !== "";
}

function emptyForm(): CorrectionForm {
  return { ...EMPTY_FORM };
}

function formatDateYYYYMMDD(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatWaterfall(markers: Array<{ name: string; time: number }>): string {
  if (markers.length === 0) {
    return "";
  }
  const base = markers[0].time;
  return markers
    .map((m, index) => {
      const absolute = m.time - base;
      const delta = index === 0 ? 0 : m.time - markers[index - 1].time;
      return `${m.name} [t+${absolute}ms, +${delta}ms]`;
    })
    .join(" -> ");
}

const CorrectionRow = memo(function CorrectionRow({
  entry,
  rowValue,
  onCommit,
  startDate,
}: {
  entry: RMCorrectionEntry;
  rowValue: CorrectionForm;
  onCommit: (key: string, nextRow: CorrectionForm) => void;
  startDate: string | null;
}) {
  const key = rowKey(entry);
  const [isEditing, setIsEditing] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [draft, setDraft] = useState<CorrectionForm>(rowValue);
  const { data, isLoading, isError, error } = useRMCorrectionBatchDetails(entry.batch, isExpanded);
  const detailTotals = useMemo(() => {
    const rows = data?.entries ?? [];
    return rows.reduce(
      (acc, row) => {
        acc.noOfComp += row.noOfComp;
        acc.calCompWt += row.calCompWt;
        acc.sfRejNos += row.sfRejNos;
        acc.suWastageNos += row.suWastageNos;
        acc.scrapKg += row.scrapKg;
        acc.partWtKg += row.partWtKg;
        acc.theoRmKg += row.theoRmKg;
        return acc;
      },
      {
        noOfComp: 0,
        calCompWt: 0,
        sfRejNos: 0,
        suWastageNos: 0,
        scrapKg: 0,
        partWtKg: 0,
        theoRmKg: 0,
      }
    );
  }, [data?.entries]);

  useEffect(() => {
    if (!isEditing) {
      setDraft(rowValue);
    }
  }, [isEditing, rowValue]);

  const updateDraft = useCallback((field: keyof CorrectionForm, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }, []);

  const toggleEdit = () => {
    if (isEditing) {
      onCommit(key, draft);
    }
    setIsEditing((prev) => !prev);
  };

  const toggleExpand = () => {
    setIsExpanded((prev) => !prev);
  };

  return (
    <>
      <TableRow hover>
        <TableCell>{entry.rawMaterial || "-"}</TableCell>
        <TableCell>
          <Button
            size="small"
            variant="text"
            onClick={toggleExpand}
            endIcon={isExpanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
            sx={{ textTransform: "none", p: 0, minWidth: 0 }}
          >
            {entry.batch}
          </Button>
        </TableCell>
        <TableCell align="right">{entry.totalInwarded.toFixed(2)}</TableCell>
        <TableCell align="right">{entry.rmGiven.toFixed(2)}</TableCell>
        <TableCell align="right">{entry.rmRemaining.toFixed(2)}</TableCell>
        <TableCell align="right">{entry.scrap.toFixed(2)}</TableCell>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              type="number"
              value={draft.rmCorrection}
              onChange={(e) => updateDraft("rmCorrection", e.target.value)}
              disabled={entry.rmRemaining === 0}
              inputProps={{ min: 0, step: "0.01" }}
              placeholder={entry.rmRemaining === 0 ? "NA" : "0.00"}
              fullWidth
            />
          ) : (
            <Typography variant="body2" color={rowValue.rmCorrection ? "text.primary" : "text.secondary"}>
              {rowValue.rmCorrection || "-"}
            </Typography>
          )}
        </TableCell>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              value={draft.rmRemarks}
              onChange={(e) => updateDraft("rmRemarks", e.target.value)}
              disabled={entry.rmRemaining === 0}
              placeholder={entry.rmRemaining === 0 ? "NA" : "Enter remarks"}
              fullWidth
            />
          ) : (
            <Typography variant="body2" color={rowValue.rmRemarks ? "text.primary" : "text.secondary"}>
              {rowValue.rmRemarks || "-"}
            </Typography>
          )}
        </TableCell>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              type="number"
              value={draft.scrapCorrection}
              onChange={(e) => updateDraft("scrapCorrection", e.target.value)}
              inputProps={{ step: "0.01" }}
              placeholder="0.00"
              fullWidth
            />
          ) : (
            <Typography variant="body2" color={rowValue.scrapCorrection ? "text.primary" : "text.secondary"}>
              {rowValue.scrapCorrection || "-"}
            </Typography>
          )}
        </TableCell>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              value={draft.scrapRemarks}
              onChange={(e) => updateDraft("scrapRemarks", e.target.value)}
              placeholder="Enter remarks"
              fullWidth
            />
          ) : (
            <Typography variant="body2" color={rowValue.scrapRemarks ? "text.primary" : "text.secondary"}>
              {rowValue.scrapRemarks || "-"}
            </Typography>
          )}
        </TableCell>
        <TableCell align="center">
          <Button
            size="small"
            variant={isEditing ? "contained" : "outlined"}
            onClick={toggleEdit}
            sx={{ textTransform: "none" }}
          >
            {isEditing ? "Done" : "Edit"}
          </Button>
        </TableCell>
      </TableRow>

      {isExpanded && (
        <TableRow>
          <TableCell colSpan={11} sx={{ bgcolor: "#fafafa" }}>
            {isLoading && <Typography variant="body2">Loading batch production details...</Typography>}
            {isError && (
              <Alert severity="error" sx={{ my: 1 }}>
                {(error as Error)?.message || "Failed to load batch details"}
              </Alert>
            )}
            {!isLoading && !isError && (
              <TableContainer component={Paper} variant="outlined" sx={{ mt: 1 }}>
                <Table
                  size="small"
                  sx={{
                    tableLayout: "fixed",
                    width: "100%",
                    "& .MuiTableCell-root": {
                      px: 0.75,
                      py: 0.5,
                      whiteSpace: "normal",
                      wordBreak: "break-word",
                      verticalAlign: "middle",
                      fontSize: 12,
                    },
                    "& .MuiTableCell-head": {
                      fontWeight: 700,
                    },
                  }}
                >
                  <TableHead>
                    <TableRow>
                      <TableCell>ProductionDate</TableCell>
                      <TableCell>Part No</TableCell>
                      <TableCell>Lot No</TableCell>
                      <TableCell>Tool</TableCell>
                      <TableCell align="right">No Of Comp</TableCell>
                      <TableCell align="right">Cal Comp Wt (Kg)</TableCell>
                      <TableCell align="right">SF Rej(Nos)</TableCell>
                      <TableCell align="right">SU Wastage(Nos)</TableCell>
                      <TableCell align="right">Scrap(Kg)</TableCell>
                      <TableCell align="right">Part Wt(Kg)</TableCell>
                      <TableCell align="right">Theo RM(Kg)</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(data?.entries ?? []).map((detail, idx) => (
                      <TableRow key={`${entry.batch}_detail_${idx}`}>
                        <TableCell>{detail.productionDate}</TableCell>
                        <TableCell>{detail.partNo || "-"}</TableCell>
                        <TableCell>{detail.lotNo || "-"}</TableCell>
                        <TableCell>{detail.tool || "-"}</TableCell>
                        <TableCell align="right">{detail.noOfComp}</TableCell>
                        <TableCell align="right">{detail.calCompWt.toFixed(4)}</TableCell>
                        <TableCell align="right">{detail.sfRejNos}</TableCell>
                        <TableCell align="right">{detail.suWastageNos}</TableCell>
                        <TableCell align="right">{detail.scrapKg.toFixed(2)}</TableCell>
                        <TableCell align="right">{detail.partWtKg.toFixed(2)}</TableCell>
                        <TableCell align="right">{detail.theoRmKg.toFixed(4)}</TableCell>
                      </TableRow>
                    ))}
                    {!!data && data.entries.length > 0 && (
                      <TableRow
                        sx={{
                          "& .MuiTableCell-root": {
                            fontWeight: 700,
                            bgcolor: "#f3f6f9",
                          },
                        }}
                      >
                        <TableCell colSpan={4}>Total</TableCell>
                        <TableCell align="right">{detailTotals.noOfComp}</TableCell>
                        <TableCell align="right">{detailTotals.calCompWt.toFixed(4)}</TableCell>
                        <TableCell align="right">{detailTotals.sfRejNos}</TableCell>
                        <TableCell align="right">{detailTotals.suWastageNos}</TableCell>
                        <TableCell align="right">{detailTotals.scrapKg.toFixed(2)}</TableCell>
                        <TableCell align="right">{detailTotals.partWtKg.toFixed(2)}</TableCell>
                        <TableCell align="right">{detailTotals.theoRmKg.toFixed(4)}</TableCell>
                      </TableRow>
                    )}
                    {(!data || data.entries.length === 0) && (
                      <TableRow>
                        <TableCell colSpan={11} align="center" sx={{ color: "text.secondary" }}>
                          No production rows found for this batch in selected date range.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  );
});

export default function RMCorrectionPage() {
  const defaultStartDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 10);
    return formatDateYYYYMMDD(d);
  }, []);

  const mountStartedAtRef = useRef<number>(Date.now());
  const fetchStartedAtRef = useRef<number | null>(null);
  const firstLoadLoggedRef = useRef(false);
  const dataReadyAtRef = useRef<number | null>(null);
  const [startDate, setStartDate] = useState<string>(defaultStartDate);
  const { data, isLoading, isError, error, isFetching, dataUpdatedAt } = useRMCorrectionEntries(startDate);
  const [form, setForm] = useState<FormState>({});
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [toast, setToast] = useState<{ open: boolean; severity: Severity; message: string }>({
    open: false,
    severity: "success",
    message: "",
  });

  const entries = useMemo(() => data?.entries ?? [], [data?.entries]);
  const displayedEntries = useMemo(() => entries.slice(0, visibleCount), [entries, visibleCount]);
  const hasMoreRows = visibleCount < entries.length;

  useEffect(() => {
    console.log("[RM Correction][Page] mount started");
  }, []);

  useEffect(() => {
    if (isFetching && fetchStartedAtRef.current === null) {
      fetchStartedAtRef.current = Date.now();
      console.log("[RM Correction][Page] data fetch lifecycle started");
    }
  }, [isFetching]);

  useEffect(() => {
    if (firstLoadLoggedRef.current) {
      return;
    }

    if (!isLoading && !isError && dataUpdatedAt > 0) {
      dataReadyAtRef.current = dataUpdatedAt;
      requestAnimationFrame(() => {
        const paintedAt = Date.now();
        const fetchStartedAt = fetchStartedAtRef.current ?? mountStartedAtRef.current;
        const apiToDataMs = dataUpdatedAt - fetchStartedAt;
        const uiRenderAfterDataMs = paintedAt - dataUpdatedAt;
        const totalPageLoadMs = paintedAt - mountStartedAtRef.current;
        const markers = [
          { name: "mount", time: mountStartedAtRef.current },
          { name: "fetchStart", time: fetchStartedAt },
          { name: "dataReady", time: dataReadyAtRef.current ?? dataUpdatedAt },
          { name: "firstPaint", time: paintedAt },
        ];

        console.log(
          `[RM Correction][Page] first load metrics -> total=${totalPageLoadMs} ms, apiLifecycle=${apiToDataMs} ms, uiRenderAfterData=${uiRenderAfterDataMs} ms, rows=${entries.length}`
        );
        console.log(`[RM Correction][Waterfall] ${formatWaterfall(markers)}`);
        firstLoadLoggedRef.current = true;
      });
    }
  }, [dataUpdatedAt, entries.length, isError, isLoading]);

  useEffect(() => {
    if (firstLoadLoggedRef.current) {
      return;
    }
    if (!isLoading && isError) {
      const endedAt = Date.now();
      const totalMs = endedAt - mountStartedAtRef.current;
      console.log(`[RM Correction][Page] first load ended with error in ${totalMs} ms`);
      firstLoadLoggedRef.current = true;
    }
  }, [isError, isLoading]);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [entries.length]);

  const commitRow = useCallback((key: string, nextRow: CorrectionForm) => {
    setForm((prev) => ({
      ...prev,
      [key]: nextRow,
    }));
  }, []);

  const showToast = (severity: Severity, message: string) => {
    setToast({ open: true, severity, message });
  };

  const loadMoreRows = useCallback(() => {
    setVisibleCount((prev) => Math.min(prev + PAGE_SIZE, entries.length));
  }, [entries.length]);

  const validateAndSubmit = () => {
    for (let i = 0; i < entries.length; i += 1) {
      const entry = entries[i];
      const key = rowKey(entry);
      const row = form[key] ?? EMPTY_FORM;

      const rmEntered = isEntered(row.rmCorrection);
      const scrapEntered = isEntered(row.scrapCorrection);

      if (rmEntered) {
        if (entry.rmRemaining === 0) {
          showToast("error", `Row ${i + 1}: RM Correction cannot be entered when RM Remaining is 0.`);
          return;
        }

        const rmValue = Number(row.rmCorrection);
        if (Number.isNaN(rmValue) || rmValue < 0) {
          showToast("error", `Row ${i + 1}: RM Correction must be a valid non-negative number.`);
          return;
        }

        if (rmValue > entry.rmRemaining) {
          showToast(
            "error",
            `Row ${i + 1}: RM Correction (${rmValue}) cannot be more than RM Remaining (${entry.rmRemaining}).`
          );
          return;
        }

        if (!isEntered(row.rmRemarks)) {
          showToast("error", `Row ${i + 1}: RM Remarks is required when RM Correction is entered.`);
          return;
        }
      }

      if (scrapEntered) {
        const scrapValue = Number(row.scrapCorrection);
        if (Number.isNaN(scrapValue)) {
          showToast("error", `Row ${i + 1}: Scrap Correction must be a valid number.`);
          return;
        }

        if (!isEntered(row.scrapRemarks)) {
          showToast("error", `Row ${i + 1}: Scrap Remarks is required when Scrap Correction is entered.`);
          return;
        }
      }
    }

    showToast("success", "Under Testing");
  };

  return (
    <Box sx={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <Box
        sx={{
          px: 3,
          py: 2,
          bgcolor: "#fff",
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <EditNoteIcon sx={{ fontSize: 28, color: "#5d4037" }} />
        <Typography variant="h5" fontWeight={700} sx={{ flexGrow: 1 }}>
          RM Correction
        </Typography>
        <TextField
          label="Start Date"
          type="date"
          size="small"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          inputProps={{ max: formatDateYYYYMMDD(new Date()) }}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 190 }}
        />
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="contained" onClick={validateAndSubmit} sx={{ textTransform: "none" }}>
          Submit
        </Button>
      </Box>

      <Box sx={{ flex: 1, p: 3 }}>
        {isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 10 }}>
            <CircularProgress />
          </Box>
        )}

        {isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {(error as Error)?.message || "Failed to load RM correction data"}
          </Alert>
        )}

        {!isLoading && !isError && (
          <TableContainer component={Paper} variant="outlined">
            <Table
              size="small"
              stickyHeader
              sx={{
                tableLayout: "fixed",
                width: "100%",
                "& .MuiTableCell-root": {
                  px: 0.75,
                  py: 0.5,
                  whiteSpace: "normal",
                  wordBreak: "break-word",
                  verticalAlign: "middle",
                  fontSize: 12,
                },
                "& .MuiTableCell-head": {
                  fontWeight: 700,
                },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: "12%" }}>Raw Material</TableCell>
                  <TableCell sx={{ width: "9%" }}>Batch</TableCell>
                  <TableCell align="right" sx={{ width: "9%" }}>
                    Total Inwarded
                  </TableCell>
                  <TableCell align="right" sx={{ width: "8%" }}>
                    RM Given
                  </TableCell>
                  <TableCell align="right" sx={{ width: "8%" }}>
                    Theo RM Remaining
                  </TableCell>
                  <TableCell align="right" sx={{ width: "7%" }}>
                    Scrap
                  </TableCell>
                  <TableCell sx={{ width: "9%" }}>Actual RM</TableCell>
                  <TableCell sx={{ width: "13%" }}>RM Remarks</TableCell>
                  <TableCell sx={{ width: "9%" }}>Actual Scrap</TableCell>
                  <TableCell sx={{ width: "13%" }}>Scrap Remarks</TableCell>
                  <TableCell align="center" sx={{ width: "9%" }}>
                    Action
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {displayedEntries.map((entry, idx) => {
                  const key = rowKey(entry);
                  return (
                    <CorrectionRow
                      key={`${key}_${idx}`}
                      entry={entry}
                      rowValue={form[key] ?? EMPTY_FORM}
                      onCommit={commitRow}
                      startDate={startDate}
                    />
                  );
                })}

                {entries.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={11} align="center" sx={{ py: 5, color: "text.secondary" }}>
                      No records found.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {!isLoading && !isError && hasMoreRows && (
          <Stack direction="row" justifyContent="center" sx={{ mt: 2 }}>
            <Button
              variant="outlined"
              startIcon={<MoreHorizIcon />}
              onClick={loadMoreRows}
              sx={{ textTransform: "none" }}
            >
              More ({Math.min(PAGE_SIZE, entries.length - visibleCount)} more)
            </Button>
          </Stack>
        )}
      </Box>

      <Snackbar
        open={toast.open}
        autoHideDuration={4000}
        onClose={() => setToast((prev) => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Alert
          onClose={() => setToast((prev) => ({ ...prev, open: false }))}
          severity={toast.severity}
          variant="filled"
          sx={{ width: "100%" }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
