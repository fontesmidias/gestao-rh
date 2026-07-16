"""Geração/atualização do catálogo de slots de documentos de um candidato.

Idempotente: cria o que falta conforme as regras condicionais e remove slots
pendentes que deixaram de se aplicar (ex.: candidato desmarcou PCD). Slots que
já receberam arquivo nunca são removidos automaticamente.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidato import Candidato
from app.models.documento import SlotDocumento, StatusSlot, TipoDocumento
from app.models.ficha import DadosPessoais, Dependente, EstadoCivil, Sexo, ValeTransporte


def _idade(nascimento: date) -> int:
    hoje = date.today()
    return hoje.year - nascimento.year - (
        (hoje.month, hoje.day) < (nascimento.month, nascimento.day)
    )


def _slots_aplicaveis(db: Session, candidato: Candidato) -> list[dict]:
    """(tipo, dependente_id, obrigatorio) que se aplicam ao estado atual da ficha."""
    pessoais = db.get(DadosPessoais, candidato.id)
    vt = db.get(ValeTransporte, candidato.id)
    dependentes = db.scalars(
        select(Dependente).where(Dependente.candidato_id == candidato.id)
    ).all()

    slots: list[dict] = [
        {"tipo": TipoDocumento.foto_3x4, "obrigatorio": True},
        {"tipo": TipoDocumento.rg, "obrigatorio": True},
        {"tipo": TipoDocumento.cpf_doc, "obrigatorio": True},
        {"tipo": TipoDocumento.ctps_digital, "obrigatorio": True},
        {"tipo": TipoDocumento.pis_comprovante, "obrigatorio": True},
        {"tipo": TipoDocumento.titulo_eleitor_doc, "obrigatorio": True},
        {"tipo": TipoDocumento.comp_endereco, "obrigatorio": True},
        # Opcional por decisão do RH (2026-07-15): nem todo cargo exige.
        {"tipo": TipoDocumento.comp_escolaridade, "obrigatorio": False},
        {"tipo": TipoDocumento.nada_consta_eleitoral, "obrigatorio": True},
        {"tipo": TipoDocumento.nada_consta_criminal, "obrigatorio": True},
        {"tipo": TipoDocumento.habilitacao_prof, "obrigatorio": False},
        {"tipo": TipoDocumento.diplomas, "obrigatorio": False},
    ]

    if pessoais is not None:
        if pessoais.sexo == Sexo.masculino and pessoais.data_nascimento is not None \
                and 18 <= _idade(pessoais.data_nascimento) <= 45:
            slots.append({"tipo": TipoDocumento.reservista, "obrigatorio": True})
        if pessoais.pcd:
            slots.append({"tipo": TipoDocumento.laudo_pcd, "obrigatorio": True})
        if pessoais.estado_civil in (EstadoCivil.casado, EstadoCivil.uniao_estavel):
            slots.append({"tipo": TipoDocumento.cert_casamento, "obrigatorio": True})

    if vt is not None and vt.optante and vt.cartao_dftrans:
        slots.append({"tipo": TipoDocumento.cartao_vt, "obrigatorio": True})

    for dep in dependentes:
        slots.append({
            "tipo": TipoDocumento.cert_nascimento_dep,
            "dependente_id": dep.id,
            "obrigatorio": True,
        })
        idade = _idade(dep.data_nascimento)
        if idade <= 6:
            slots.append({
                "tipo": TipoDocumento.cartao_vacina_dep,
                "dependente_id": dep.id,
                "obrigatorio": True,
            })
        elif idade <= 14:
            slots.append({
                "tipo": TipoDocumento.declaracao_escolar_dep,
                "dependente_id": dep.id,
                "obrigatorio": True,
            })

    return slots


def sincronizar_slots(db: Session, candidato: Candidato) -> list[SlotDocumento]:
    existentes = db.scalars(
        select(SlotDocumento).where(SlotDocumento.candidato_id == candidato.id)
    ).all()
    por_chave: dict[tuple[TipoDocumento, uuid.UUID | None], SlotDocumento] = {
        (s.tipo, s.dependente_id): s for s in existentes
    }

    aplicaveis = _slots_aplicaveis(db, candidato)
    chaves_aplicaveis = set()
    for spec in aplicaveis:
        chave = (spec["tipo"], spec.get("dependente_id"))
        chaves_aplicaveis.add(chave)
        slot = por_chave.get(chave)
        if slot is None:
            slot = SlotDocumento(
                candidato_id=candidato.id,
                tipo=spec["tipo"],
                dependente_id=spec.get("dependente_id"),
                obrigatorio=spec["obrigatorio"],
            )
            db.add(slot)
        else:
            slot.obrigatorio = spec["obrigatorio"]

    # Remove apenas slots pendentes que deixaram de se aplicar.
    for chave, slot in por_chave.items():
        if chave not in chaves_aplicaveis and slot.status == StatusSlot.pendente:
            db.delete(slot)

    db.flush()
    return db.scalars(
        select(SlotDocumento)
        .where(SlotDocumento.candidato_id == candidato.id)
        .order_by(SlotDocumento.criado_em)
    ).all()
