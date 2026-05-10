"""DeepLOB-style CNN/LSTM scaffold."""

from __future__ import annotations

import torch
from torch import nn


class DeepLOBCNNLSTM(nn.Module):
    """CNN feature extractor plus LSTM temporal head for future-return regression."""

    def __init__(
        self,
        num_features: int = 40,
        hidden_size: int = 64,
        num_lstm_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.num_features = num_features
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=(1, 2), padding=(0, 1)),
            nn.ReLU(),
            nn.BatchNorm2d(16),
            nn.Conv2d(16, 32, kernel_size=(4, 1), padding=(2, 0)),
            nn.ReLU(),
            nn.BatchNorm2d(32),
            nn.Conv2d(32, 32, kernel_size=(4, 1), padding=(1, 0)),
            nn.ReLU(),
            nn.BatchNorm2d(32),
        )
        lstm_dropout = dropout if num_lstm_layers > 1 else 0.0
        self.lstm = nn.LSTM(
            input_size=32,
            hidden_size=hidden_size,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=lstm_dropout,
        )
        head_size = max(1, hidden_size // 2)
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, head_size),
            nn.ReLU(),
            nn.Linear(head_size, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3:
            raise ValueError("expected input shaped [batch, window, features]")
        if x.shape[-1] != self.num_features:
            raise ValueError(f"expected {self.num_features} features, got {x.shape[-1]}")

        z = self.cnn(x.unsqueeze(1))
        z = z.mean(dim=3).transpose(1, 2)
        out, _ = self.lstm(z)
        return self.head(out[:, -1, :]).squeeze(-1)
