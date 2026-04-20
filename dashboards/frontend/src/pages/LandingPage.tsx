import { Link as RouterLink } from "react-router-dom";
import type { ReactNode } from "react";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import BuildIcon from "@mui/icons-material/Build";
import HandymanIcon from "@mui/icons-material/Handyman";
import AssessmentIcon from "@mui/icons-material/Assessment";
import QueryStatsIcon from "@mui/icons-material/QueryStats";
import EditNoteIcon from "@mui/icons-material/EditNote";
import { useAuth } from "../auth/AuthContext";
import Button from "@mui/material/Button";
import { hasAccess, type DashboardKey } from "../auth/permissions";

const dashboards: Array<{
  title: string;
  description: string;
  path: string;
  icon: ReactNode;
  color: string;
  accessKey?: DashboardKey;
}> = [
  {
    title: "Tools",
    description: "Tool scheduling, machine assignments, usage analytics & maintenance planning",
    path: "/dashboards/tools",
    icon: <BuildIcon sx={{ fontSize: 48 }} />,
    color: "#d84315",
    accessKey: "tools",
  },
  {
    title: "Preventive Maintenance",
    description: "Track tool maintenance schedules, stroke thresholds & maintenance history",
    path: "/preventive-maintenance",
    icon: <HandymanIcon sx={{ fontSize: 48 }} />,
    color: "#00796b",
    accessKey: "preventive_maintenance",
  },
  {
    title: "Life Report",
    description: "Tool life tracking, stroke analysis & lifecycle reporting",
    path: "/life-report",
    icon: <AssessmentIcon sx={{ fontSize: 48 }} />,
    color: "#1976d2",
    accessKey: "life_report",
  },
  {
    title: "Reports",
    description: "Save SQL queries, run reports and review tabular outputs in one place",
    path: "/reports",
    icon: <QueryStatsIcon sx={{ fontSize: 48 }} />,
    color: "#455a64",
    accessKey: "reports",
  },
  {
    title: "RM Correction",
    description: "Adjust raw material stock entries and apply manual correction updates",
    path: "/rm-correction",
    icon: <EditNoteIcon sx={{ fontSize: 48 }} />,
    color: "#5d4037",
  },
];

export default function LandingPage() {
  const { permissions, user, logout } = useAuth();

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", py: 4, px: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
        <Typography variant="h3" fontWeight={700} gutterBottom>
          Dashboards
        </Typography>
        {user && (
          <Button variant="outlined" onClick={logout} sx={{ textTransform: "none" }}>
            Logout
          </Button>
        )}
      </Box>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 5 }}>
        Select a dashboard or tool to get started.
      </Typography>

      <Grid container spacing={3}>
        {dashboards.map((d) => {
          const enabled = d.accessKey ? hasAccess(permissions, d.accessKey) : true;
          return (
          <Grid key={d.path} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
            <Card
              sx={{
                height: "100%",
                transition: "transform 0.15s, box-shadow 0.15s",
                "&:hover": {
                  transform: "translateY(-4px)",
                  boxShadow: 6,
                },
                ...(enabled
                  ? {}
                  : {
                      opacity: 0.5,
                      filter: "grayscale(0.6)",
                      boxShadow: "none",
                    }),
              }}
            >
              <CardActionArea
                component={RouterLink}
                to={d.path}
                sx={{ height: "100%" }}
                disabled={!enabled}
              >
                <CardContent
                  sx={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    textAlign: "center",
                    py: 4,
                    gap: 2,
                  }}
                >
                  <Box sx={{ color: d.color }}>{d.icon}</Box>
                  <Typography variant="h6" fontWeight={600}>
                    {d.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {d.description}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        );
        })}
      </Grid>
    </Box>
  );
}
