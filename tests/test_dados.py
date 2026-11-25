import sys

from robo_agregado import dados, enviar_fretes


def test_pasta_padrao_em_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("ROBO_AGREGADO_DADOS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert dados.pasta_dados() == tmp_path / "RoboAgregado"


def test_pasta_pela_variavel(monkeypatch, tmp_path):
    monkeypatch.setenv("ROBO_AGREGADO_DADOS", str(tmp_path / "x"))
    assert dados.pasta_dados() == tmp_path / "x"


def test_config_criado_na_primeira_execucao(tmp_path):
    cfg = tmp_path / "nova" / "config.ini"
    cfg.parent.mkdir()
    dados.atualizar_config_embutido(cfg, "2.0.0")
    assert "[email]" in cfg.read_text(encoding="utf-8")
    assert (tmp_path / "nova" / "config.versao").read_text(encoding="utf-8").strip() == "2.0.0"


def test_config_da_mesma_versao_nao_e_trocado(tmp_path):
    cfg = tmp_path / "config.ini"
    dados.atualizar_config_embutido(cfg, "2.0.0")
    cfg.write_text("editado", encoding="utf-8")
    dados.atualizar_config_embutido(cfg, "2.0.0")
    assert cfg.read_text(encoding="utf-8") == "editado"
    assert not (tmp_path / "config.ini.bak").exists()


def test_config_substituido_quando_versao_muda(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("editado", encoding="utf-8")
    (tmp_path / "config.versao").write_text("1.3.3", encoding="utf-8")
    dados.atualizar_config_embutido(cfg, "2.0.0")
    assert (tmp_path / "config.ini.bak").read_text(encoding="utf-8") == "editado"
    assert "[email]" in cfg.read_text(encoding="utf-8")
    assert (tmp_path / "config.versao").read_text(encoding="utf-8").strip() == "2.0.0"


def test_versao_embutida_mais_antiga_nao_toca_em_nada(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("editado", encoding="utf-8")
    (tmp_path / "config.versao").write_text("2.1.0", encoding="utf-8")
    dados.atualizar_config_embutido(cfg, "2.0.0")
    assert cfg.read_text(encoding="utf-8") == "editado"
    assert not (tmp_path / "config.ini.bak").exists()
    assert (tmp_path / "config.versao").read_text(encoding="utf-8") == "2.1.0"


def test_marca_vazia_troca_o_config(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("editado", encoding="utf-8")
    (tmp_path / "config.versao").write_text("", encoding="utf-8")
    dados.atualizar_config_embutido(cfg, "2.0.0")
    assert (tmp_path / "config.ini.bak").read_text(encoding="utf-8") == "editado"
    assert "[email]" in cfg.read_text(encoding="utf-8")


def test_marca_nao_numerica_troca_o_config(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("editado", encoding="utf-8")
    (tmp_path / "config.versao").write_text("abc", encoding="utf-8")
    dados.atualizar_config_embutido(cfg, "2.0.0")
    assert "[email]" in cfg.read_text(encoding="utf-8")


def test_comparacao_numerica_de_versoes(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("editado", encoding="utf-8")
    (tmp_path / "config.versao").write_text("2.9.0", encoding="utf-8")
    dados.atualizar_config_embutido(cfg, "2.10.0")  # 2.10.0 > 2.9.0 (e não o contrário, como texto)
    assert "[email]" in cfg.read_text(encoding="utf-8")


def test_atualizacao_ativa_com_config_malformado(monkeypatch, tmp_path):
    _preparar_config(monkeypatch, tmp_path, "[atualizacao]\nativo = sim\nativo = nao\n")
    assert dados.atualizacao_ativa() is True


def _preparar_config(monkeypatch, tmp_path, conteudo):
    monkeypatch.setattr(dados, "PASTA", tmp_path)
    (tmp_path / "config.ini").write_text(conteudo, encoding="utf-8")
    (tmp_path / "config.versao").write_text(dados.__version__, encoding="utf-8")


def test_atualizacao_ativa(monkeypatch, tmp_path):
    _preparar_config(monkeypatch, tmp_path, "[atualizacao]\nativo = nao\n")
    assert dados.atualizacao_ativa() is False
    _preparar_config(monkeypatch, tmp_path, "[atualizacao]\nativo = SIM\n")
    assert dados.atualizacao_ativa() is True
    _preparar_config(monkeypatch, tmp_path, "[email]\nmetodo = smtp\n")
    assert dados.atualizacao_ativa() is True


def test_migra_arquivos_de_ao_lado_do_exe(monkeypatch, tmp_path):
    exe = tmp_path / "exe"
    exe.mkdir()
    destino = tmp_path / "dados"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(dados, "PASTA", destino)

    monkeypatch.setattr(sys, "executable", str(exe / "RoboAgregado.exe"))
    (exe / ".env").write_text("A=1", encoding="utf-8")
    dados.preparar_pasta()
    assert (destino / ".env").read_text(encoding="utf-8") == "A=1"
    assert not (exe / ".env").exists()

    monkeypatch.setattr(sys, "executable", str(exe / "SistemaFinanceiro.exe"))
    (exe / "log_envios.csv").write_text("x", encoding="utf-8")
    dados.preparar_pasta()
    assert (exe / "log_envios.csv").exists()
    assert not (destino / "log_envios.csv").exists()


def test_carregar_config_padrao_usa_pasta_de_dados():
    cfg = enviar_fretes.carregar_config()
    assert enviar_fretes.metodo_envio(cfg) == "microsoft"
    assert (dados.PASTA / "config.ini").exists()
