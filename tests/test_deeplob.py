import pytest

torch = pytest.importorskip("torch")

from strategies.crypto.research.deeplob import DeepLOBCNNLSTM


def test_deeplob_forward_shape_and_backward():
    model = DeepLOBCNNLSTM(num_features=40, hidden_size=16, num_lstm_layers=1, dropout=0.0)
    x = torch.randn(4, 20, 40)
    y = model(x)
    loss = y.pow(2).mean()

    loss.backward()

    assert y.shape == (4,)
    assert any(param.grad is not None for param in model.parameters())
