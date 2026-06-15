import React, { useCallback, useState } from 'react';
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Alert,
  AppBar,
  Box,
  Button,
  CssBaseline,
  Snackbar,
  ThemeProvider,
  Toolbar,
  Typography,
  createTheme,
} from '@mui/material';
import AssessmentIcon from '@mui/icons-material/Assessment';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import HistoryIcon from '@mui/icons-material/History';
import RuleIcon from '@mui/icons-material/Rule';

import AnalyzingPage from './pages/AnalyzingPage';
import DashboardPage from './pages/DashboardPage';
import HistoryPage from './pages/HistoryPage';
import ReportPage from './pages/ReportPage';
import StandardsPage from './pages/StandardsPage';
import UploadPage from './pages/UploadPage';

const theme = createTheme({
  palette: {
    primary: { main: '#14532d', light: '#2f855a', dark: '#0f3d25' },
    secondary: { main: '#1d4ed8' },
    background: { default: '#f6f7f4', paper: '#ffffff' },
    success: { main: '#15803d' },
    warning: { main: '#b45309' },
    error: { main: '#b91c1c' },
  },
  typography: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h4: { fontWeight: 750, letterSpacing: 0 },
    h5: { fontWeight: 720, letterSpacing: 0 },
    h6: { fontWeight: 700, letterSpacing: 0 },
    button: { textTransform: 'none', fontWeight: 650, letterSpacing: 0 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          boxShadow: '0 1px 3px rgba(15, 23, 42, 0.08)',
          border: '1px solid rgba(15, 23, 42, 0.08)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8 },
      },
    },
  },
});

interface ToastState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'warning' | 'info';
}

export const ToastContext = React.createContext<{
  showToast: (message: string, severity?: ToastState['severity']) => void;
}>({
  showToast: () => undefined,
});

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [toast, setToast] = useState<ToastState>({
    open: false,
    message: '',
    severity: 'info',
  });

  const showToast = useCallback((message: string, severity: ToastState['severity'] = 'info') => {
    setToast({ open: true, message, severity });
  }, []);

  const closeToast = useCallback(() => {
    setToast((prev) => ({ ...prev, open: false }));
  }, []);

  const navItems = [
    { to: '/', label: '新建分析', icon: <CloudUploadIcon /> },
    { to: '/history', label: '分析记录', icon: <HistoryIcon /> },
    { to: '/standards', label: '评价标准', icon: <RuleIcon /> },
  ];

  const isAnalyzing = location.pathname.includes('/analyzing');

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ToastContext.Provider value={{ showToast }}>
        <AppBar position="sticky" elevation={0} sx={{ bgcolor: '#ffffff', color: '#111827', borderBottom: '1px solid #e5e7eb' }}>
          <Toolbar sx={{ gap: 2, minHeight: 64 }}>
            <AssessmentIcon sx={{ color: 'primary.main' }} />
            <Box onClick={() => navigate('/')} sx={{ cursor: 'pointer', mr: 2 }}>
              <Typography variant="h6" sx={{ lineHeight: 1 }}>
                课堂质量分析
              </Typography>
              <Typography variant="caption" color="text.secondary">
                教师授课能力评价工作台
              </Typography>
            </Box>
            <Box sx={{ flexGrow: 1 }} />
            {!isAnalyzing && (
              <Box sx={{ display: 'flex', gap: 1 }}>
                {navItems.map((item) => {
                  const active = location.pathname === item.to;
                  return (
                    <Button
                      key={item.to}
                      component={Link}
                      to={item.to}
                      startIcon={item.icon}
                      variant={active ? 'contained' : 'text'}
                      color={active ? 'primary' : 'inherit'}
                    >
                      {item.label}
                    </Button>
                  );
                })}
              </Box>
            )}
          </Toolbar>
        </AppBar>

        <Box component="main" sx={{ minHeight: 'calc(100vh - 64px)' }}>
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/tasks/:id/analyzing" element={<AnalyzingPage />} />
            <Route path="/tasks/:id/dashboard" element={<DashboardPage />} />
            <Route path="/tasks/:id/report" element={<ReportPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/standards" element={<StandardsPage />} />
          </Routes>
        </Box>

        <Snackbar
          open={toast.open}
          autoHideDuration={5000}
          onClose={closeToast}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert onClose={closeToast} severity={toast.severity} variant="filled" sx={{ width: '100%' }}>
            {toast.message}
          </Alert>
        </Snackbar>
      </ToastContext.Provider>
    </ThemeProvider>
  );
}

export default App;
