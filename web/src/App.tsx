import React, { useState, useCallback } from 'react';
import { Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom';
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  AppBar,
  Toolbar,
  Typography,
  Box,
  Snackbar,
  Alert,
  Button,
} from '@mui/material';
import UploadIcon from '@mui/icons-material/CloudUpload';
import HistoryIcon from '@mui/icons-material/History';
import SchoolIcon from '@mui/icons-material/School';

import UploadPage from './pages/UploadPage';
import AnalyzingPage from './pages/AnalyzingPage';
import DashboardPage from './pages/DashboardPage';
import ReportPage from './pages/ReportPage';
import HistoryPage from './pages/HistoryPage';
import StandardsPage from './pages/StandardsPage';

// 蓝色主题
const theme = createTheme({
  palette: {
    primary: {
      main: '#1565c0',
      light: '#1e88e5',
      dark: '#0d47a1',
    },
    secondary: {
      main: '#2e7d32',
      light: '#4caf50',
      dark: '#1b5e20',
    },
    background: {
      default: '#f5f7fa',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
        },
      },
    },
  },
});

// 全局错误提示 Context
interface ToastState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'warning' | 'info';
}

export const ToastContext = React.createContext<{
  showToast: (message: string, severity?: ToastState['severity']) => void;
}>({
  showToast: () => {},
});

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [toast, setToast] = useState<ToastState>({
    open: false,
    message: '',
    severity: 'info',
  });

  const showToast = useCallback(
    (message: string, severity: ToastState['severity'] = 'info') => {
      setToast({ open: true, message, severity });
    },
    [],
  );

  const handleCloseToast = useCallback(() => {
    setToast((prev) => ({ ...prev, open: false }));
  }, []);

  const isAnalyzing = location.pathname.includes('/analyzing');

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ToastContext.Provider value={{ showToast }}>
        {/* 顶部导航栏 */}
        <AppBar position="sticky" elevation={1} sx={{ bgcolor: 'white', color: 'primary.main' }}>
          <Toolbar>
            <SchoolIcon sx={{ mr: 1, fontSize: 28 }} />
            <Typography
              variant="h6"
              sx={{ fontWeight: 700, cursor: 'pointer', flexGrow: 0, mr: 4 }}
              onClick={() => navigate('/')}
            >
              火花课堂视频分析
            </Typography>

            <Box sx={{ flexGrow: 1 }} />

            {!isAnalyzing && (
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  component={Link}
                  to="/"
                  startIcon={<UploadIcon />}
                  color={location.pathname === '/' ? 'primary' : 'inherit'}
                  variant={location.pathname === '/' ? 'contained' : 'text'}
                  size="small"
                >
                  上传分析
                </Button>
                <Button
                  component={Link}
                  to="/history"
                  startIcon={<HistoryIcon />}
                  color={location.pathname === '/history' ? 'primary' : 'inherit'}
                  variant={location.pathname === '/history' ? 'contained' : 'text'}
                  size="small"
                >
                  历史记录
                </Button>
                <Button
                  component={Link}
                  to="/standards"
                  startIcon={<SchoolIcon />}
                  color={location.pathname === '/standards' ? 'primary' : 'inherit'}
                  variant={location.pathname === '/standards' ? 'contained' : 'text'}
                  size="small"
                >
                  评价标准
                </Button>
              </Box>
            )}
          </Toolbar>
        </AppBar>

        {/* 路由页面 */}
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

        {/* 全局错误提示 */}
        <Snackbar
          open={toast.open}
          autoHideDuration={5000}
          onClose={handleCloseToast}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert onClose={handleCloseToast} severity={toast.severity} variant="filled" sx={{ width: '100%' }}>
            {toast.message}
          </Alert>
        </Snackbar>
      </ToastContext.Provider>
    </ThemeProvider>
  );
}

export default App;
