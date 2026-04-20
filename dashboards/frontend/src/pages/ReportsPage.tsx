import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import DialogContentText from "@mui/material/DialogContentText";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Divider from "@mui/material/Divider";
import AddIcon from "@mui/icons-material/Add";
import DescriptionIcon from "@mui/icons-material/Description";
import FolderIcon from "@mui/icons-material/Folder";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import {
  useCreateGroup,
  useCreateReport,
  useDeleteGroup,
  useDeleteReport,
  useReportGroups,
  useReports,
  useUpdateReport,
} from "@/api";
import { useAuth } from "../auth/AuthContext";
import { hasPlusAccess } from "../auth/permissions";

function CreateGroupDialog({
  open,
  onClose,
  onCreate,
  isPending,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => void;
  isPending: boolean;
}) {
  const [name, setName] = useState("");

  const handleClose = () => {
    setName("");
    onClose();
  };

  const handleCreate = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onCreate(trimmed);
    setName("");
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>Create Group</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          fullWidth
          margin="dense"
          label="Group Name"
          placeholder="e.g. Tools"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={handleCreate} disabled={isPending || !name.trim()}>
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function CreateReportDialog({
  open,
  onClose,
  onCreate,
  groupName,
  isPending,
  title,
  actionLabel,
  initialName,
  initialQueryTemplate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (payload: { name: string; queryTemplate: string }) => void;
  groupName: string;
  isPending: boolean;
  title?: string;
  actionLabel?: string;
  initialName?: string;
  initialQueryTemplate?: string;
}) {
  const [name, setName] = useState("");
  const [queryTemplate, setQueryTemplate] = useState("");

  useEffect(() => {
    if (open) {
      setName(initialName ?? "");
      setQueryTemplate(initialQueryTemplate ?? "");
    }
  }, [open, initialName, initialQueryTemplate]);

  const detectedVariables = useMemo(() => {
    const re = /\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}/g;
    const found = new Set<string>();
    let match: RegExpExecArray | null = null;

    while ((match = re.exec(queryTemplate)) !== null) {
      found.add(match[1]);
    }

    return Array.from(found);
  }, [queryTemplate]);

  const handleClose = () => {
    setName("");
    setQueryTemplate("");
    onClose();
  };

  const handleCreate = () => {
    const trimmedName = name.trim();
    const trimmedQuery = queryTemplate.trim();
    if (!trimmedName || !trimmedQuery) return;

    onCreate({ name: trimmedName, queryTemplate: trimmedQuery });
    setName("");
    setQueryTemplate("");
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>{title ?? `Create Report in ${groupName}`}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <TextField
          autoFocus
          label="Report Name"
          placeholder="e.g. Tools with cavity threshold"
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
        />
        <TextField
          label="SQL Query Template"
          placeholder="select tool where cavity >= {cavity}"
          value={queryTemplate}
          onChange={(e) => setQueryTemplate(e.target.value)}
          multiline
          minRows={6}
          fullWidth
        />
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
          <Typography variant="body2" color="text.secondary">
            Variables detected:
          </Typography>
          {detectedVariables.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              None
            </Typography>
          ) : (
            detectedVariables.map((v) => <Chip key={v} size="small" label={`{${v}}`} />)
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleCreate}
          disabled={isPending || !name.trim() || !queryTemplate.trim()}
        >
          {actionLabel ?? "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function ReportsPage() {
  const { permissions } = useAuth();
  const canEdit = hasPlusAccess(permissions, "reports");
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [reportDialogOpen, setReportDialogOpen] = useState(false);
  const [editingReport, setEditingReport] = useState<{
    id: string;
    name: string;
    queryTemplate: string;
  } | null>(null);
  const [deletingGroup, setDeletingGroup] = useState<{ id: string; name: string } | null>(null);
  const [deletingReport, setDeletingReport] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: groups = [] } = useReportGroups();
  const { data: reports = [] } = useReports(selectedGroupId);

  const createGroup = useCreateGroup();
  const createReport = useCreateReport();
  const updateReport = useUpdateReport();
  const deleteGroup = useDeleteGroup();
  const deleteReport = useDeleteReport();

  const selectedGroup = groups.find((g) => g.id === selectedGroupId) ?? null;

  useEffect(() => {
    if (!selectedGroupId && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const handleCreateGroup = (name: string) => {
    createGroup.mutate(name, {
      onSuccess: (group) => {
        setGroupDialogOpen(false);
        setSelectedGroupId(group.id);
        setError(null);
      },
      onError: (err) => setError(err.message),
    });
  };

  const handleCreateReport = (payload: { name: string; queryTemplate: string }) => {
    if (!selectedGroupId) return;

    createReport.mutate(
      {
        groupId: selectedGroupId,
        ...payload,
      },
      {
        onSuccess: (report) => {
          setReportDialogOpen(false);
          openReportRunTab(report.id);
          setError(null);
        },
        onError: (err) => setError(err.message),
      },
    );
  };

  const openReportRunTab = (reportId: string) => {
    const url = `/reports/run?reportId=${encodeURIComponent(reportId)}`;
    window.location.assign(url);
  };

  const handleEditReport = (payload: { name: string; queryTemplate: string }) => {
    if (!editingReport || !selectedGroupId) return;

    updateReport.mutate(
      {
        reportId: editingReport.id,
        groupId: selectedGroupId,
        name: payload.name,
        queryTemplate: payload.queryTemplate,
      },
      {
        onSuccess: () => {
          setEditingReport(null);
          setError(null);
        },
        onError: (err) => setError(err.message),
      },
    );
  };

  const handleDeleteGroup = () => {
    if (!deletingGroup) return;

    deleteGroup.mutate(deletingGroup.id, {
      onSuccess: () => {
        if (selectedGroupId === deletingGroup.id) {
          const nextGroup = groups.find((g) => g.id !== deletingGroup.id);
          setSelectedGroupId(nextGroup?.id ?? null);
        }
        setDeletingGroup(null);
        setError(null);
      },
      onError: (err) => setError(err.message),
    });
  };

  const handleDeleteReport = () => {
    if (!deletingReport || !selectedGroupId) return;

    deleteReport.mutate(
      {
        reportId: deletingReport.id,
        groupId: selectedGroupId,
      },
      {
        onSuccess: () => {
          setDeletingReport(null);
          setError(null);
        },
        onError: (err) => setError(err.message),
      },
    );
  };

  return (
    <Box sx={{ px: 3, py: 3, height: "100%", display: "flex", flexDirection: "column", gap: 2 }}>
      <Box>
        <Typography variant="h4" fontWeight={700} gutterBottom>
          Reports
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Create groups and report definitions. Open any report in a new tab to run it.
        </Typography>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ flexGrow: 1, minHeight: 0, minWidth: 0 }}>
        <Paper sx={{ width: { xs: "100%", md: 280 }, display: "flex", flexDirection: "column", minHeight: 0, flexShrink: 0 }}>
          <Box sx={{ p: 2, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <Typography variant="h6" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <FolderIcon fontSize="small" />
              Groups
            </Typography>
            <Button
              size="small"
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setGroupDialogOpen(true)}
              disabled={!canEdit}
            >
              Add
            </Button>
          </Box>
          <Divider />
          <List sx={{ overflowY: "auto", flexGrow: 1 }}>
            {groups.map((group) => (
              <Box key={group.id} sx={{ display: "flex", alignItems: "center", pr: 1 }}>
                <ListItemButton
                  selected={selectedGroupId === group.id}
                  onClick={() => setSelectedGroupId(group.id)}
                  sx={{ flex: 1, minWidth: 0 }}
                >
                  <ListItemText primary={group.name} />
                </ListItemButton>
                <IconButton
                  size="small"
                  color="error"
                  aria-label={`Delete group ${group.name}`}
                  onClick={() => setDeletingGroup({ id: group.id, name: group.name })}
                  disabled={!canEdit}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Box>
            ))}
            {groups.length === 0 && (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  No groups yet. Create one to get started.
                </Typography>
              </Box>
            )}
          </List>
        </Paper>

        <Paper sx={{ flex: 1, minWidth: 0, p: 2, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2 }}>
            <Box>
              <Typography variant="h6">
                {selectedGroup ? `Reports: ${selectedGroup.name}` : "Select a group"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Open a report in a new tab to run and rerun with variables.
              </Typography>
            </Box>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              disabled={!selectedGroup || !canEdit}
              onClick={() => setReportDialogOpen(true)}
            >
              New Report
            </Button>
          </Box>

          {selectedGroup ? (
            <Stack spacing={1.5} sx={{ minHeight: 0, height: "100%", overflowY: "auto", pr: 0.5 }}>
              {reports.map((report) => (
                <Paper key={report.id} variant="outlined" sx={{ p: 1.25 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, minWidth: 0 }}>
                    <Box sx={{ minWidth: 0, flex: 1, display: "flex", alignItems: "center", gap: 1 }}>
                      <Typography variant="subtitle2" fontWeight={700}>
                        <DescriptionIcon sx={{ fontSize: 18, mr: 1, verticalAlign: "text-bottom" }} />
                        {report.name}
                      </Typography>
                      {report.variables.length > 0
                        ? <Chip size="small" label={`${report.variables.length} inputs`} />
                        : <Chip size="small" label="No inputs" />}
                    </Box>

                    <Stack direction={{ xs: "column", sm: "row" }} spacing={0.75} sx={{ flexShrink: 0 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<EditIcon />}
                        onClick={() =>
                          setEditingReport({
                            id: report.id,
                            name: report.name,
                            queryTemplate: report.queryTemplate,
                          })
                        }
                        disabled={!canEdit}
                      >
                        Edit
                      </Button>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<OpenInNewIcon />}
                        onClick={() => openReportRunTab(report.id)}
                      >
                        Open
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteIcon />}
                        onClick={() => setDeletingReport({ id: report.id, name: report.name })}
                        disabled={!canEdit}
                      >
                        Delete
                      </Button>
                    </Stack>
                  </Box>
                </Paper>
              ))}
              {reports.length === 0 && (
                <Box sx={{ p: 2, border: "1px dashed", borderColor: "divider", borderRadius: 2 }}>
                  <Typography variant="body2" color="text.secondary">
                    No reports in this group yet.
                  </Typography>
                </Box>
              )}
            </Stack>
          ) : (
            <Box
              sx={{
                flexGrow: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px dashed",
                borderColor: "divider",
                borderRadius: 2,
              }}
            >
              <Typography color="text.secondary">Choose a group from the left panel.</Typography>
            </Box>
          )}
        </Paper>
      </Stack>

      <CreateGroupDialog
        open={groupDialogOpen}
        onClose={() => setGroupDialogOpen(false)}
        onCreate={handleCreateGroup}
        isPending={createGroup.isPending}
      />

      <CreateReportDialog
        open={reportDialogOpen}
        onClose={() => setReportDialogOpen(false)}
        onCreate={handleCreateReport}
        groupName={selectedGroup?.name ?? ""}
        isPending={createReport.isPending}
        title={`Create Report in ${selectedGroup?.name ?? ""}`}
        actionLabel="Create"
      />

      <CreateReportDialog
        open={!!editingReport}
        onClose={() => setEditingReport(null)}
        onCreate={handleEditReport}
        groupName={selectedGroup?.name ?? ""}
        isPending={updateReport.isPending}
        title="Edit Report"
        actionLabel="Save"
        initialName={editingReport?.name}
        initialQueryTemplate={editingReport?.queryTemplate}
      />

      <Dialog open={!!deletingGroup} onClose={() => setDeletingGroup(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete Group</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Delete group "{deletingGroup?.name}" and all reports inside it?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeletingGroup(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={handleDeleteGroup} disabled={deleteGroup.isPending}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!deletingReport} onClose={() => setDeletingReport(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete Report</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Delete report "{deletingReport?.name}"?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeletingReport(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={handleDeleteReport} disabled={deleteReport.isPending}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
