import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Autocomplete from "@mui/material/Autocomplete";
import { useAdminUsers, useRbacStore, useUpdateUserPermissions } from "../api";
import type { DashboardKey } from "../auth/permissions";

const PLUS_ACCESS_ALLOWED: DashboardKey[] = ["preventive_maintenance", "reports"];

export default function RbacAdminPage() {
  const { data: users = [], isLoading: usersLoading } = useAdminUsers();
  const { data: rbac, isLoading: rbacLoading } = useRbacStore();
  const updatePermissions = useUpdateUserPermissions();
  const [selectedUserId, setSelectedUserId] = useState<number | "">("");
  const [access, setAccess] = useState<DashboardKey[]>([]);
  const [plusAccess, setPlusAccess] = useState<DashboardKey[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [userQuery, setUserQuery] = useState("");

  const selectedUser = users.find((u) => u.id === selectedUserId) ?? null;
  const dashboards = rbac?.dashboards ?? [];

  const userOptions = useMemo(() => {
    const q = userQuery.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => {
      const fullName = `${u.firstName} ${u.lastName}`.trim().toLowerCase();
      return (
        u.login.toLowerCase().includes(q) ||
        fullName.includes(q) ||
        String(u.id).includes(q)
      );
    });
  }, [users, userQuery]);

  useEffect(() => {
    if (!selectedUserId) {
      setAccess([]);
      setPlusAccess([]);
    }
  }, [selectedUserId]);

  useEffect(() => {
    if (!rbac || !selectedUserId) return;
    const existing = rbac.users.find((u) => u.userId === selectedUserId);
    setAccess(existing?.access ?? []);
    setPlusAccess(existing?.plusAccess ?? []);
  }, [rbac, selectedUserId]);

  const isLoading = usersLoading || rbacLoading;

  const handleToggle = (key: DashboardKey) => {
    setAccess((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
    setPlusAccess((prev) => prev.filter((k) => k !== key));
  };

  const handleTogglePlus = (key: DashboardKey) => {
    setPlusAccess((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const canSave = selectedUserId !== "" && !updatePermissions.isPending;

  const handleSave = () => {
    if (!selectedUserId || !selectedUser) return;
    setError(null);
    updatePermissions.mutate(
      {
        userId: selectedUser.id,
        login: selectedUser.login,
        access,
        plusAccess: plusAccess.filter((k) => access.includes(k)),
      },
      {
        onError: (err) => setError(err.message),
      }
    );
  };

  const dashboardLabels = useMemo(() => {
    return {
      tools: "Tools",
      preventive_maintenance: "Preventive Maintenance",
      life_report: "Life Report",
      production: "Production",
      rm_variance: "RM Variance",
      reports: "Reports",
    } as Record<DashboardKey, string>;
  }, []);

  return (
    <Box sx={{ px: 3, py: 3, height: "100%", display: "flex", flexDirection: "column", gap: 2 }}>
      <Box>
        <Typography variant="h4" fontWeight={700} gutterBottom>
          RBAC Admin
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Assign dashboard access and edit permissions per user.
        </Typography>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          {isLoading ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <Autocomplete
                options={userOptions}
                value={selectedUser}
                onChange={(_, value) => setSelectedUserId(value?.id ?? "")}
                inputValue={userQuery}
                onInputChange={(_, value) => setUserQuery(value)}
                getOptionLabel={(u) =>
                  `${u.login}${u.firstName || u.lastName ? ` - ${u.firstName} ${u.lastName}` : ""} (#${u.id})`
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderInput={(params) => (
                  <TextField {...params} label="Search user" placeholder="Type login, name, or ID" fullWidth />
                )}
              />

              <Divider />

              <Box>
                <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                  Access
                </Typography>
                <Stack spacing={1}>
                  {dashboards.map((key) => (
                    <FormControlLabel
                      key={key}
                      control={
                        <Checkbox
                          checked={access.includes(key)}
                          onChange={() => handleToggle(key)}
                        />
                      }
                      label={dashboardLabels[key]}
                    />
                  ))}
                </Stack>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                  Plus Access (edit/delete)
                </Typography>
                <Stack spacing={1}>
                  {dashboards.map((key) => (
                    <FormControlLabel
                      key={key}
                      control={
                        <Checkbox
                          checked={plusAccess.includes(key)}
                          onChange={() => handleTogglePlus(key)}
                          disabled={!access.includes(key) || !PLUS_ACCESS_ALLOWED.includes(key)}
                        />
                      }
                      label={dashboardLabels[key]}
                    />
                  ))}
                </Stack>
              </Box>

              <Button variant="contained" onClick={handleSave} disabled={!canSave}>
                {updatePermissions.isPending ? "Saving..." : "Save Changes"}
              </Button>
            </>
          )}
        </Stack>
      </Paper>
    </Box>
  );
}
