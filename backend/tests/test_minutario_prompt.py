"""Teste unitário da montagem do prompt do Minutário — sem banco, sem rede
(api/minutario.py::_prompt_usuario é lógica pura de formatação).

Cobre a regra do C1: NENHUM dado de candidato entra na chamada à IA — só
campos da vaga. E que campos vazios não geram linhas "a definir" no prompt
(a instrução do sistema pede isso, mas o prompt do usuário já não deveria
oferecer a chance).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_minutario_prompt.py
"""

from app.api.minutario import ComporMensagemIn, _prompt_usuario

# Sem nenhum campo preenchido -> mensagem genérica de divulgação
vazio = ComporMensagemIn()
prompt_vazio = _prompt_usuario(vazio, None)
assert "genérica" in prompt_vazio.lower(), prompt_vazio
assert "Banco de Talentos" in prompt_vazio

# Só tom preenchido -> aparece o tom, cai no genérico pros demais campos
so_tom = ComporMensagemIn(tom="descontraído")
prompt_tom = _prompt_usuario(so_tom, None)
assert "descontraído" in prompt_tom
assert "genérica" in prompt_tom.lower()

# Campos da vaga preenchidos -> viram linhas "- Rótulo: valor"
completo = ComporMensagemIn(
    tom="cordial e direto", cargo="Auxiliar de Serviços Gerais", regime="efetivo",
    salario="R$ 1.700,00", local="Águas Claras/DF", escala="12x36",
    jornada="44h semanais", horario="08h às 17h",
    requisitos_obrigatorios="CNH categoria B",
    requisitos_desejaveis="experiência anterior",
    instrucoes_extra="enviar currículo até sexta", prazo="até 05/08",
)
prompt_completo = _prompt_usuario(completo, None)
assert "cordial e direto" in prompt_completo
assert "- Cargo/função: Auxiliar de Serviços Gerais" in prompt_completo
assert "- Salário: R$ 1.700,00" in prompt_completo
assert "- Requisitos obrigatórios: CNH categoria B" in prompt_completo
assert "genérica" not in prompt_completo.lower()  # não deveria cair no genérico

# Campo vazio (string vazia ou None) NÃO vira linha "a definir" — é omitido
so_cargo = ComporMensagemIn(cargo="Vigia", salario="")
prompt_so_cargo = _prompt_usuario(so_cargo, None)
assert "- Cargo/função: Vigia" in prompt_so_cargo
assert "Salário" not in prompt_so_cargo
assert "a definir" not in prompt_so_cargo.lower()

# Modelo de referência entra como estrutura, não como dado da vaga
com_modelo = ComporMensagemIn(cargo="Porteiro")
prompt_com_modelo = _prompt_usuario(com_modelo, "Olá! Temos uma vaga incrível.")
assert "Olá! Temos uma vaga incrível." in prompt_com_modelo
assert "modelo de ESTRUTURA" in prompt_com_modelo

# Regra central do C1: NENHUM campo de nome/telefone/e-mail de candidato existe
# no schema de entrada — a garantia é estrutural (ComporMensagemIn não tem
# esses campos), não uma checagem em runtime.
campos_do_schema = set(ComporMensagemIn.model_fields.keys())
proibidos = {"nome", "candidato_nome", "telefone", "email", "cpf", "candidato_id"}
assert not (campos_do_schema & proibidos), campos_do_schema & proibidos

print("test_minutario_prompt: OK")
