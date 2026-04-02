# Como fazer o build do IN9USBAgent

O build é feito inteiramente via **GitHub Actions** em um runner Windows. Não é necessário ter Python, PyInstaller ou Inno Setup instalados localmente.

---

## O que o build gera

| Arquivo | Descrição |
|---|---|
| `usb_agent.exe` | Executável único (PyInstaller, ~20 MB) — sem dependências externas |
| `IN9USBAgent_Setup.exe` | Instalador completo (Inno Setup) — distribua este para os colaboradores |

---

## Como disparar o build

### Opção 1 — Nova versão (recomendado)

Use este fluxo ao lançar uma versão nova para distribuição. Ele cria uma **GitHub Release** com o instalador disponível para download.

```bash
# 1. Faça as alterações no código e comite normalmente
git add .
git commit -m "descrição do que mudou"
git push origin main

# 2. Crie a tag da versão (padrão: vMAJOR.MINOR.PATCH)
git tag v1.0.2
git push origin v1.0.2
```

Após o push da tag, o GitHub Actions inicia automaticamente. Em ~5 minutos o instalador estará disponível na aba **Releases** do repositório.

> **Importante:** lembre de atualizar `#define AppVersion` em `installer/setup.iss` antes de criar a tag.

---

### Opção 2 — Build manual (sem criar release)

Use para testar o build sem publicar uma versão oficial.

1. Acesse o repositório no GitHub
2. Clique em **Actions** → **Build Installer**
3. Clique em **Run workflow** → **Run workflow**

O instalador ficará disponível em **Actions → job → Artifacts** por 30 dias. Não cria Release nem tag.

---

## Como acessar o instalador após o build

### Via Release (Opção 1)
1. Acesse o repositório no GitHub
2. Clique em **Releases** (coluna direita)
3. Clique na release mais recente
4. Baixe o arquivo `IN9USBAgent_Setup.exe`

### Via Artifacts (Opção 2)
1. Acesse **Actions** → clique no job mais recente
2. Role até a seção **Artifacts**
3. Baixe `IN9USBAgent-<ref>`

---

## Etapas do pipeline (`.github/workflows/build.yml`)

```
1. Checkout do repositório
2. Python 3.11
3. pip install: pyinstaller, wmi, pywin32, psutil, requests, pystray, Pillow
4. PyInstaller → dist/usb_agent.exe  (executável único, sem console)
5. Chocolatey instala Inno Setup 6
6. iscc installer/setup.iss → dist/IN9USBAgent_Setup.exe
7. Upload dos artefatos (30 dias)
8. Cria GitHub Release com o instalador (somente em push de tag)
```

O runner é `windows-latest` (Windows Server 2022) — necessário porque `wmi` e `pywin32` são bibliotecas exclusivas do Windows.

---

## Versionamento

A versão do instalador é definida em dois lugares que devem estar sincronizados:

| Arquivo | Campo |
|---|---|
| `installer/setup.iss` | `#define AppVersion "1.0.1"` |

O nome da tag Git (`v1.0.1`) aparece automaticamente no nome da Release e do artefato.

### Padrão de versão

```
vMAJOR.MINOR.PATCH

MAJOR — mudanças incompatíveis (ex: novo formato de payload)
MINOR — novas funcionalidades (ex: novo tipo de dispositivo)
PATCH — correções de bug (ex: fix no uninstaller)
```

---

## Histórico de versões

| Versão | Tag | Descrição |
|---|---|---|
| 1.0.0 | v1.0.0 | MVP: serviço Windows + monitoramento USB + ícone na bandeja |
| 1.0.1 | v1.0.1 | Uninstaller apaga `agent.db` — garantia de token novo na reinstalação |
