import sys
with open("frontend/src/pages/PreventiveMaintenancePage.tsx", "r", encoding="utf-8") as f:
    text = f.read()

start_str = "export default function PreventiveMaintenancePage() {"
start_idx = text.find(start_str)

new_str = """export default function PreventiveMaintenancePage() {
  const [addOpen, setAddOpen] = useState(false);
  const [editEntry, setEditEntry] = useState<PMEntry | null>(null);
  const [confirmEntry, setConfirmEntry] = useState<PMEntry | null>(null);
  const [deleteEntry, setDeleteEntry] = useState<PMEntry | null>(null);
  const [historyEntry, setHistoryEntry] = useState<PMEntry | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [configureToolId, setConfigureToolId] = useState<number | null>(null);

  const { data: entries = [], isLoading: entriesLoading } = usePMEntries();
  const { data: allTools = [], isLoading: toolsLoading } = useAllTools();

  // Set of already-added toolIds (for disabling in add dialog)
  const existingToolIds = useMemo(
    () => new Set(entries.map((e) => e.toolId)),
    [entries]
  );

  // Create a map from toolId to PMEntry for quick lookup
  const pmEntryMap = useMemo(
    () => new Map(entries.map((e) => [e.toolId, e])),
    [entries]
  );

  // Join all tools with PM records, filter by search
  const displayedTools = useMemo(() => {
    const q = searchFilter.toLowerCase().trim();
    return allTools.filter((tool) =>
      q === "" || tool.toolNo.toLowerCase().includes(q)
    );
  }, [allTools, searchFilter]);

  // Get last maintenance date for a tool
  const getLastMaintenanceDate = (toolId: number): string => {
    const entry = pmEntryMap.get(toolId);
    if (!entry || !entry.maintenanceHistory || entry.maintenanceHistory.length === 0) {
      return "—";
    }
    const lastRecord = entry.maintenanceHistory[entry.maintenanceHistory.length - 1];
    return new Date(lastRecord.date).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  };

  const isLoading = entriesLoading || toolsLoading;

  return (
    <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
      {/* Top bar */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          mb: 3,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="h5" fontWeight={700} sx={{ flexShrink: 0 }}>
          Preventive Maintenance
        </Typography>

        <TextField
          size="small"
          placeholder="Search tools..."
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          sx={{ flexGrow: 1, maxWidth: 400 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
      </Box>

      {/* Content */}
      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
          <CircularProgress />
        </Box>
      ) : displayedTools.length === 0 ? (
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            mt: 8,
            color: "text.secondary",
          }}
        >
          <BuildIcon sx={{ fontSize: 64, mb: 2, opacity: 0.3 }} />
          <Typography variant="h6">
            {searchFilter
              ? "No tools match your search"
              : "No tools available"}
          </Typography>
        </Box>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: "grey.100" }}>
                <TableCell sx={{ fontWeight: 600 }}>Tool No</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Tool Life
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  PM Strokes
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  SPM
                </TableCell>
                <TableCell sx={{ fontWeight: 600 }}>
                  Last Maintenance
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600 }}>
                  Actions
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {displayedTools.map((tool) => {
                const pmEntry = pmEntryMap.get(tool.id);
                const isConfigured = !!pmEntry;

                return (
                  <TableRow key={tool.id} hover>
                    <TableCell>{tool.toolNo}</TableCell>
                    <TableCell align="right">
                      {isConfigured
                        ? formatIndianNumber(pmEntry.toolLife)
                        : "—"}
                    </TableCell>
                    <TableCell align="right">
                      {isConfigured
                        ? formatIndianNumber(pmEntry.pmStrokes)
                        : "—"}
                    </TableCell>
                    <TableCell align="right">
                      {isConfigured ? pmEntry.spm : "—"}
                    </TableCell>
                    <TableCell>
                      {isConfigured ? getLastMaintenanceDate(tool.id) : "—"}
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: "flex", gap: 1, justifyContent: "center" }}>
                        {isConfigured ? (
                          <>
                            <Tooltip title="View History">
                              <IconButton
                                size="small"
                                onClick={() => setHistoryEntry(pmEntry)}
                              >
                                <HistoryIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Edit">
                              <IconButton
                                size="small"
                                onClick={() => setEditEntry(pmEntry)}
                              >
                                <EditIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Confirm Maintenance">
                              <IconButton
                                size="small"
                                onClick={() => setConfirmEntry(pmEntry)}
                              >
                                <CheckCircleIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Delete">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => setDeleteEntry(pmEntry)}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </>
                        ) : (
                          <Tooltip title="Configure Tool">
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={<SettingsIcon />}
                              onClick={() => setConfigureToolId(tool.id)}
                            >
                              Configure
                            </Button>
                          </Tooltip>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Dialogs */}
      <AddToolDialog
        open={addOpen || configureToolId !== null}
        onClose={() => {
          setAddOpen(false);
          setConfigureToolId(null);
        }}
        existingToolIds={existingToolIds}
        initialTool={
          configureToolId !== null
            ? allTools.find((t) => t.id === configureToolId) ?? null
            : null
        }
      />
      <EditDialog
        open={!!editEntry}
        onClose={() => setEditEntry(null)}
        entry={editEntry}
      />
      <ConfirmMaintenanceDialog
        open={!!confirmEntry}
        onClose={() => setConfirmEntry(null)}
        entry={confirmEntry}
      />
      <DeleteDialog
        open={!!deleteEntry}
        onClose={() => setDeleteEntry(null)}
        entry={deleteEntry}
      />
      <MaintenanceHistoryDialog
        open={!!historyEntry}
        onClose={() => setHistoryEntry(null)}
        entry={historyEntry}
      />
    </Box>
  );
}
"""

text = text[:start_idx] + new_str
with open("frontend/src/pages/PreventiveMaintenancePage.tsx", "w", encoding="utf-8") as f:
    f.write(text)
print("Done")

