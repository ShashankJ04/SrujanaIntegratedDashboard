import { useState, useRef } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import MenuIcon from "@mui/icons-material/Menu";
import HomeIcon from "@mui/icons-material/Home";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import DashboardIcon from "@mui/icons-material/Dashboard";
import BuildIcon from "@mui/icons-material/Build";
import HandymanIcon from "@mui/icons-material/Handyman";
import AssessmentIcon from "@mui/icons-material/Assessment";
import QueryStatsIcon from "@mui/icons-material/QueryStats";
import EditNoteIcon from "@mui/icons-material/EditNote";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { useAuth } from "../auth/AuthContext";
import { hasAccess, type DashboardKey } from "../auth/permissions";

const DRAWER_WIDTH = 240;

type NavItem = {
  label: string;
  icon: React.ReactNode;
  path: string;
  accessKey?: DashboardKey;
  adminOnly?: boolean;
};

const navItems: NavItem[] = [
  { label: "Home", icon: <HomeIcon />, path: "/" },
  { label: "Tools", icon: <BuildIcon />, path: "/dashboards/tools", accessKey: "tools" },
  { label: "Preventive Maintenance", icon: <HandymanIcon />, path: "/preventive-maintenance", accessKey: "preventive_maintenance" },
  { label: "Life Report", icon: <AssessmentIcon />, path: "/life-report", accessKey: "life_report" },
  { label: "Reports", icon: <QueryStatsIcon />, path: "/reports", accessKey: "reports" },
  { label: "RM Correction", icon: <EditNoteIcon />, path: "/rm-correction" },
  { label: "RBAC Admin", icon: <DashboardIcon />, path: "/admin/rbac", adminOnly: true },
];

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [appBarVisible, setAppBarVisible] = useState(false);
  const hideTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const location = useLocation();
  const { permissions, user, logout } = useAuth();

  const showBar = () => {
    if (hideTimeout.current) clearTimeout(hideTimeout.current);
    setAppBarVisible(true);
  };

  const hideBar = () => {
    hideTimeout.current = setTimeout(() => setAppBarVisible(false), 300);
  };

  const drawerContent = (
    <>
      <Toolbar />
      <List>
        {navItems.map((item) => {
          if (item.adminOnly && !user?.isAdmin) {
            return null;
          }
          const disabled = item.accessKey ? !hasAccess(permissions, item.accessKey) : false;
          const linkProps = disabled
            ? { component: "div" as const }
            : { component: RouterLink, to: item.path };

          return (
            <ListItemButton
              key={item.label}
              {...linkProps}
              disabled={disabled}
              selected={location.pathname === item.path}
              onClick={() => setDrawerOpen(false)}
              sx={disabled ? { opacity: 0.5 } : undefined}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          );
        })}
      </List>
    </>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      {/* Invisible hover trigger zone at the top of the screen */}
      <Box
        onMouseEnter={showBar}
        sx={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          height: "6px",
          zIndex: (t) => t.zIndex.drawer + 2,
        }}
      />

      {/* App bar — slides down from above on hover */}
      <AppBar
        position="fixed"
        onMouseEnter={showBar}
        onMouseLeave={hideBar}
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          transform: appBarVisible ? "translateY(0)" : "translateY(-100%)",
          transition: "transform 0.3s ease",
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            onClick={() => setDrawerOpen(!drawerOpen)}
            sx={{ mr: 2 }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap>
            Manufacturing Dashboard
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <Button color="inherit" onClick={logout} sx={{ textTransform: "none" }}>
            Logout
          </Button>
        </Toolbar>
      </AppBar>

      {/* Drawer — temporary on all screen sizes, closed by default */}
      <Drawer
        variant="temporary"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sx={{
          "& .MuiDrawer-paper": { width: DRAWER_WIDTH },
        }}
      >
        {drawerContent}
      </Drawer>

      {/* Main content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          display: "flex",
          flexDirection: "column",
          height: "100vh",
          overflow: "auto",
          backgroundColor: "background.default",
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
