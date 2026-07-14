"""Validações de documentos brasileiros."""


def cpf_valido(cpf: str) -> bool:
    """Valida os dígitos verificadores do CPF (algoritmo oficial da Receita)."""
    numeros = "".join(c for c in cpf if c.isdigit())
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(numeros[i]) * ((posicao + 1) - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[posicao]):
            return False
    return True
