import React from 'react';
import { Box, Step, StepLabel, Stepper, Typography } from '@mui/material';
import type { TaskStatusType } from '../api/client';

const STEPS = [
  { label: '提取音频', status: 'extracting' as TaskStatusType },
  { label: '语音转写', status: 'transcribing' as TaskStatusType },
  { label: '智能分析', status: 'analyzing' as TaskStatusType },
  { label: '生成报告', status: 'scoring' as TaskStatusType },
];

const STATUS_TO_STEP: Record<TaskStatusType, number> = {
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
              <StepLabel>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: isActive ? 700 : 500,
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
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 2, minHeight: 22 }}>
        {status === 'completed' ? '分析完成' : currentStage}
      </Typography>
    </Box>
  );
};

export default StepProgress;
