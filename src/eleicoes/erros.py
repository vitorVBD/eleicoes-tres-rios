"""Erros de negócio do pipeline, com mensagem clara para quem opera a ferramenta."""


class ErroPipeline(Exception):
    """Falha esperada: arquivo ausente, coluna fora do padrão ou município sem linhas."""
