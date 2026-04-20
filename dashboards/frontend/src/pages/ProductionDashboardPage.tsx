import { useState, useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import SearchIcon from "@mui/icons-material/Search";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import FactoryIcon from "@mui/icons-material/Factory";
import { useProductionByDate } from "@/api";
import type { ProductionEntry } from "@/api";
import { formatIndianNumber } from "@/utils";

// ── Helpers ────────────────────────────────────────────────────────

/** Convert YYYY-MM-DD date input value → DDMMYYYY API param */
function toApiDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-");
  return `${d}${m}${y}`;
}

/** Format ISO date to readable DD/MM/YYYY */
function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

// ── Variance chip ──────────────────────────────────────────────────

function VarianceChip({ value }: { value: number }) {
  if (value === 0) {
    return <Chip label="0" size="small" sx={{ fontWeight: 600, fontSize: 12 }} />;
  }
  const isPositive = value > 0;
  return (
    <Chip
      icon={isPositive ? <TrendingUpIcon /> : <TrendingDownIcon />}
      label={formatIndianNumber(Math.abs(value))}
      size="small"
      color={isPositive ? "success" : "error"}
      variant="outlined"
      sx={{ fontWeight: 600, fontSize: 12 }}
    />
  );
}

// ── Column config ──────────────────────────────────────────────────

interface Column {
  key: keyof ProductionEntry;
  label: string;
  align?: "left" | "right" | "center";
  format?: (v: any, row: ProductionEntry) => React.ReactNode;
  width?: number;
}

const columns: Column[] = [
  { key: "customer", label: "Customer", width: 110 },
  { key: "partno", label: "Part No", width: 90 },
  { key: "partname", label: "Part Name", width: 100 },
  { key: "rawMaterial", label: "RM", width: 80 },
  {
    key: "scheduledDate",
    label: "Pln Dt",
    width: 75,
    format: (v: string) => (v ? formatDate(v) : "—"),
  },
  {
    key: "scheduledQty",
    label: "Pln Qty",
    align: "right",
    width: 65,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "prodQty",
    label: "Prod Qty",
    align: "right",
    width: 65,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "variance",
    label: "Var",
    align: "center",
    width: 75,
    format: (v: number) => <VarianceChip value={v} />,
  },
  {
    key: "setupWastage",
    label: "SW",
    align: "right",
    width: 45,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "sfRejection",
    label: "SF",
    align: "right",
    width: 45,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "netQty",
    label: "Grs Qty",
    align: "right",
    width: 65,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "issuedQty",
    label: "RM Isu",
    align: "right",
    width: 65,
    format: (v: number) => v.toFixed(2),
  },
  {
    key: "requiredQty",
    label: "RM Rqd",
    align: "right",
    width: 65,
    format: (v: number) => v.toFixed(2),
  },
  {
    key: "fgStock",
    label: "FG",
    align: "right",
    width: 60,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "wipStock",
    label: "WIP",
    align: "right",
    width: 60,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "totalStock",
    label: "Total Stk",
    align: "right",
    width: 65,
    format: (v: number) => formatIndianNumber(v),
  },
];

// ── Main Page ──────────────────────────────────────────────────────

export default function ProductionDashboardPage() {
  // Default to yesterday
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const defaultDate = yesterday.toISOString().slice(0, 10);
  const [selectedDate, setSelectedDate] = useState(defaultDate);
  const [queryDate, setQueryDate] = useState<string | null>(toApiDate(defaultDate));

  const { data, isLoading, isError, error } = useProductionByDate(queryDate);

  const handleSearch = () => {
    if (selectedDate) {
      setQueryDate(toApiDate(selectedDate));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  // Sort entries by customer then partno
  const sortedEntries = useMemo(
    () => data?.entries?.slice().sort((a, b) =>
      a.customer.localeCompare(b.customer) || a.partno.localeCompare(b.partno)
    ) ?? [],
    [data?.entries]
  );

  const totals = data?.totals;

  // Compute stock totals from entries
  const stockTotals = useMemo(() => {
    if (!sortedEntries.length) return { fg: 0, wip: 0, total: 0 };
    return sortedEntries.reduce(
      (acc, e) => ({
        fg: acc.fg + e.fgStock,
        wip: acc.wip + e.wipStock,
        total: acc.total + e.totalStock,
      }),
      { fg: 0, wip: 0, total: 0 }
    );
  }, [sortedEntries]);

  return (
    <Box
      sx={{
        minHeight: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Header bar ─────────────────────────────────────────── */}
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
        <FactoryIcon sx={{ fontSize: 28, color: "#7b1fa2" }} />
        <Typography variant="h5" fontWeight={700} sx={{ flexGrow: 1 }}>
          Production Dashboard
        </Typography>

        <TextField
          type="date"
          size="small"
          label="Production Date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          onKeyDown={handleKeyDown}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 200 }}
        />
        <Button
          variant="contained"
          startIcon={<SearchIcon />}
          onClick={handleSearch}
          sx={{ textTransform: "none" }}
        >
          Search
        </Button>
      </Box>

      {/* ── Content ────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, p: 3 }}>
        {isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 10 }}>
            <CircularProgress />
          </Box>
        )}

        {isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {(error as Error)?.message || "Failed to load production data"}
          </Alert>
        )}

        {data && (
          <>
            {/* ── Table ───────────────────────────────────────── */}
            <TableContainer
              component={Paper}
              variant="outlined"
              sx={{
                "& .MuiTableCell-root": {
                  px: 1,
                  py: 0.5,
                },
                "& .MuiTableCell-head": {
                  bgcolor: "#f5f5f5",
                  fontWeight: 700,
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                  whiteSpace: "nowrap",
                  position: "sticky",
                  top: 0,
                  zIndex: 1,
                },
                "& .MuiTableCell-body": {
                  fontSize: 12,
                },
              }}
            >
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: 50, fontWeight: 700 }}>#</TableCell>
                    {columns.map((col) => (
                      <TableCell
                        key={col.key}
                        align={col.align ?? "left"}
                        sx={{ minWidth: col.width }}
                      >
                        {col.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedEntries.map((entry, idx) => (
                    <TableRow
                      key={idx}
                      hover
                      sx={{
                        "&:nth-of-type(even)": {
                          bgcolor: "action.hover",
                        },
                      }}
                    >
                      <TableCell sx={{ color: "text.secondary" }}>
                        {idx + 1}
                      </TableCell>
                      {columns.map((col) => (
                        <TableCell key={col.key} align={col.align ?? "left"}>
                          {col.format
                            ? col.format(entry[col.key], entry)
                            : (entry[col.key] as any) ?? "—"}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}

                  {/* ── Totals row ──────────────────────────── */}
                  <TableRow
                    sx={{
                      "& .MuiTableCell-root": {
                        fontWeight: 700,
                        borderTop: "2px solid",
                        borderColor: "divider",
                        bgcolor: "#fafafa",
                        fontSize: 13,
                      },
                    }}
                  >
                    <TableCell />
                    <TableCell colSpan={5}>
                      <strong>TOTAL</strong>
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals!.scheduledQty)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals!.prodQty)}
                    </TableCell>
                    <TableCell align="center">
                      <VarianceChip value={totals!.variance} />
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals!.setupWastage)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals!.sfRejection)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals!.netQty)}
                    </TableCell>
                    <TableCell align="right">
                      {totals!.issuedQty.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {totals!.requiredQty.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(stockTotals.fg)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(stockTotals.wip)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(stockTotals.total)}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}

        {/* Empty state before first search */}
        {!data && !isLoading && !isError && (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              py: 10,
              color: "text.secondary",
            }}
          >
            <FactoryIcon sx={{ fontSize: 64, mb: 2, opacity: 0.3 }} />
            <Typography variant="h6">
              Select a date and click Search to view production data
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
