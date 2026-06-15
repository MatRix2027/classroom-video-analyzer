import React from 'react';
import { Box, Step, StepLabel, Stepper, Typography } from '@mui/material';
import type { TaskStatusType } from '../api/client';

// 四阶段定义
const STEPS = [
  { label: '提取音频', status: 'extracting' as TaskStatusType },
  { label: '语音识别', status: 'transcribing' as TaskStatusType },
  { label: '智能分析', status: 'analyzing' as TaskStatusType },
  { label: '生成报告', status: 'scoring' as TaskStatusType },
];

// 状态到步骤索引映射
const STATUS_TO_STEP: Record<string, number> = {
  pending: -1,
  extracting: 0,
  transcribing: 1,
  analyzing: 2,
  scoring: 3,
  completed: 4,
  failed: -1,
};

interface StepProgressProps {
  status: TaskStatusType;
  currentStage: string;
}

/** 四阶段步骤进度条 */
const StepProgress: React.FC<StepProgressProps> = ({ status, currentStage }) => {
  const activeStep = STATUS_TO_STEP[status] ?? -1;

  return (
    <Box sx={{ width: '100%', py: 2 }}>
      <Stepper activeStep={activeStep} alternativeLabel>
        {STEPS.map((step, index) => {
          const isActive = index === activeStep;
          const isCompleted = index < activeStep || status === 'completed';

          return (
            <Step key={step.label} completed={isCompleted}>
              <StepLabel
                StepIconProps={{
                  sx: {
                    '&.Mui-active': {
                      color: '#1565c0',
                      animation: isActive ? 'pulse 1.5s ease-in-out infinite' : 'none',
                    },
                    '&.Mui-completed': {
                      color: '#2e7d32',
                    },
                  },
                }}
              >
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: isActive ? 700 : 400,
                    color: isActive ? 'primary.main' : isCompleted ? 'success.main' : 'text.secondary',
                  }}
                >
                  {step.label}
                </Typography>
              </StepLabel>
            </Step>
          );
        })}
      </Stepper>

      {/* 当前阶段描述 */}
      {currentStage && (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ textAlign: 'center', mt: 2 }}
        >
          {status === 'completed' ? '分析完成' : currentStage}
        </Typography>
      )}

      {/* 动画样式 */}
      <style>{`
        @keyframes pulse {
          0% { transform: scale(1); }
          50% { transform: scale(1.15); }
          100% { transform: scale(1); }
        }
      `}</style>
    </Box>
  );
};

export default StepProgress;
