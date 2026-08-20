# Conectar o assistente ao portal

Este é o caminho recomendado: **dois cliques e o seu login**, sem instalar nada.

> Se você prefere rodar o servidor no seu próprio computador (ou precisa dele
> sem internet), o guia manual continua valendo — veja `README.md`.

## O que você vai conseguir fazer

Depois de conectar, dá para perguntar ao Claude:

- *"Por que o dossiê da Kátia não gera?"* — ele responde com a causa, em vez de
  você procurar na tela.
- *"O que falta na admissão do João?"*
- *"Quem está com documento pendente hoje?"*
- *"O que trava a exportação para o Tirvu?"*
- *"Cadastra este currículo no Banco de Talentos."*

**O que ele não faz, por decisão e não por limitação técnica:** efetivar,
desligar, decidir reembolso-creche, assinar documento e exportar a base. Esses
atos mudam vínculo, dinheiro ou o sistema inteiro, e continuam pedindo uma
pessoa olhando a tela. Se você pedir, ele responde que não pode.

## Conectar (uma vez)

1. No Claude, vá em **Configurações → Conectores → Adicionar conector
   personalizado**.
2. Cole o endereço do portal — o mesmo que você usa para entrar, por exemplo
   `https://rh.suaempresa.com.br/mcp`
3. Clique em **Adicionar** e depois em **Conectar**.
4. Abre a tela de login **do portal**. Entre com o seu e-mail e senha de sempre.
5. Leia a tela de autorização — ela diz para onde as informações vão e o que o
   assistente poderá fazer — e clique em **Autorizar**.

Pronto. As ferramentas aparecem e você já pode perguntar.

**Não há token para criar nem para colar.** Você entra com a conta que já tem.

## Quem pode conectar

Os perfis **RH**, **Administrador** e **Superadministrador**.

Se o seu perfil for outro, você faz login normalmente e vê uma tela explicando —
não é erro, é acesso não liberado. Quem administra o portal pode ajustar o seu
perfil em Configurações → Equipe. **O seu acesso ao portal pela tela continua
normal** de qualquer forma.

## O assistente age com menos permissões que você

Isso é de propósito. Ele executa instruções que vêm de texto — e, neste sistema,
o texto vem de currículo, de anotação e de campo livre, escritos por gente de
fora. Uma superfície menor limita o estrago se alguém tentar manipulá-lo.

Se um cadastro contiver instruções escondidas dirigidas a uma IA (às vezes em
letra branca, invisível na tela), o assistente **avisa você** em vez de obedecer
— e mostra o texto como dado, nunca como comando.

## Cortar o acesso

Em **Configurações → 🔌 E-mail e integrações → 🔗 Conexões do assistente**, quem
administra o portal vê quem conectou e corta com um clique. O efeito é
imediato.

Desativar a conta de alguém no portal **também** corta o assistente dela — não
há um segundo lugar para lembrar de revogar.

## Quando não funciona

| O que aparece | O que é | O que fazer |
|---|---|---|
| "Não foi possível conectar ao servidor" | O endereço está errado, ou o portal está fora do ar | Abra o endereço no navegador. Se o portal abre e o conector não conecta, avise quem administra |
| "Seu acesso ao assistente não está liberado" | Seu perfil não é RH/Administrador | Peça a mudança de perfil a quem administra |
| "E-mail ou senha não conferem" | Credencial do portal | É o mesmo login da tela. Se esqueceu, use "esqueci a senha" no portal |
| "Esta ação não é permitida para o assistente" | O ato pedido é dos que só a tela faz | Faça pela tela — não é defeito |
| O assistente parou de funcionar de repente | A conexão foi cortada, ou sua conta foi desativada | Conecte de novo; se persistir, fale com quem administra |

## Para quem administra o portal

A variável **`MCP_ISSUER`** precisa estar no `.env` de cada ambiente, com o
endereço público do portal:

```
MCP_ISSUER=https://rh.suaempresa.com.br
```

Três regras: `https://` com domínio real (não aceita `http` nem IP), **sem barra
no final**, e **vazia desliga** o assistente — o portal segue funcionando
normalmente.

⚠️ Ela não é deduzida do endereço de acesso de propósito: é o endereço que o
portal *afirma* ser o dele, e quem falsificasse um cabeçalho de requisição
conseguiria fazê-lo afirmar outro.

Para conferir se está no ar: `GET /mcp/health` responde `{"status":"ok"}` quando
configurado, e `sem_issuer` quando falta a variável.
