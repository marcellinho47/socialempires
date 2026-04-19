## Flash Continuation
To play Social Empires you'll need either a *flash-capable browser*, or the *Adobe Flash Player* and a *browser with Flash support*:

:mag: **Flash-capable Browsers**

> [FlashBrowser](https://github.com/radubirsan/FlashBrowser/releases/latest)
> 
> *Note:* Flash-capable browsers like FlashBrowser integrate a Flash Player and therefore do not require an *Adobe Flash Player* installation.

:flashlight: **Adobe Flash Player**

> [Download Flash Player](https://archive.org/download/flashplayerarchive/pub/flashplayer/installers/archive/fp_32.0.0.371_archive.zip/32_0_r0_371%2Fflashplayer32_0r0_371_win.exe) for **Firefox** and **Basilisk** – NPAPI
> 
> [Download Flash Player](https://archive.org/download/flashplayerarchive/pub/flashplayer/installers/archive/fp_32.0.0.371_archive.zip/32_0_r0_371%2Fflashplayer32_0r0_371_winpep.exe) for Opera and **Chromium** based applications – PPAPI
>
> *Note:* All downloads are for Flash Player [32.0.0.371](https://archive.org/download/flashplayerarchive/pub/flashplayer/installers/archive/fp_32.0.0.371_archive.zip/), the last version without [End-of-Life](https://www.adobe.com/products/flashplayer/end-of-life.html) kill switch, from the Adobe Inc. [Flash Player Archive](https://archive.org/download/flashplayerarchive/).

:mag: **Browsers with Flash support**

> [Chromium 82.0](https://chromium.en.uptodown.com/windows/download/2181158), the open-source projects behind the Google Chrome browser.
>
> [Firefox 84.0 64-bit](https://download-installer.cdn.mozilla.net/pub/firefox/releases/84.0/win64/en-US/Firefox%20Setup%2084.0.exe) or [32-bit](https://download-installer.cdn.mozilla.net/pub/firefox/releases/84.0/win32/en-US/Firefox%20Setup%2084.0.exe) (14 Dec 2020), the final version to support Flash.
> 
> **Important:** By default, Firefox is set for automatic updates. To prevent Firefox from automatically updating itself after you install an older version, you'll need to change your Firefox update settings: Click the menu button (三) and select *Options*. In the *General* panel, go to the *Firefox Updates* section.
> 
> **Important:** By default, Flash is disabled in Chromium. You need to enable Flash in Chromium settings.
> 
> [Basilisk Browser](https://www.basilisk-browser.org/), which fully supports all NPAPI plugins (i.e. Flash). It's a fork of the Mozilla/Firefox code.

---

## Ruffle — limitações conhecidas

Rodar o jogo pelo emulador [Ruffle](https://ruffle.rs/) (via `/ruffle.html` no servidor local) é a forma mais acessível hoje, principalmente em macOS/Linux e em navegadores modernos. Alguns comportamentos do jogo original não funcionam perfeitamente pois dependem de partes do AS3 que o Ruffle ainda não implementa totalmente, ou de integrações externas (Facebook SDK) que não existem neste fork de preservação.

Resumo do que está degradado/não-funcional sob Ruffle:

### Aba NEWS (painel BUILD)
- **O que deveria fazer:** rotacionar items especiais de cash semanalmente.
- **Estado atual:** tende a mostrar poucos ou nenhum item. A lógica de rotação é hardcoded no SWF (AS3); o servidor só envia o catálogo completo. Ruffle parece não executar essa parte da UI corretamente.
- **Fix:** exigiria decompilar o SWF com [JPEXS](https://github.com/jindrapetrik/jpexs-decompiler), localizar a lógica de seleção e recompilar.

### Botão "Add Ally"
- **O que deveria fazer:** abrir convite do Facebook (`FBConnect.api()`).
- **Estado atual:** clique sem reação. Ruffle não emula a ponte JavaScript ↔ Flash que chama o SDK do Facebook. Não há infraestrutura local para substituir o convite do FB.
- **Fix possível:** criar um shim em `ExternalInterface` via [página HTML que hospeda o Ruffle](templates/ruffle.html) interceptando a chamada e abrindo um endpoint próprio de convite por email. Estimativa: 2-4h; fora do escopo atual.

### Descrições em Storage / BUILD para items adicionados por patches
- **O que deveria aparecer:** texto descritivo quando você passa o mouse sobre itens no storage ou no painel de build.
- **Estado atual:** muitos aparecem com texto vazio ou "CASE NOT FOUND".
- **Causa:** o SWF busca descrição com base em um mapeamento AS3 hardcoded de `subcat_functional` → string em `localization_strings`. Novos items (Soul Mixer, Hell's Forge, Dragon Boss, unidades do unit_patch, etc.) reutilizam `subcat_functional` existentes, mas aparentemente o switch no AS3 tem cases limitados e para alguns não cai em lugar nenhum.
- **Por que não dá para corrigir só no config:** adicionar strings novas à `localization_strings` não ajuda — o SWF não consulta por ID de item, consulta por chave fixa. Precisaria adicionar novos cases no AS3.
- **Fix:** decompilar o SWF, adicionar cases faltantes no switch de descrição, recompilar. Escopo estimado: 4-8h.

### Em suma
Os 3 pontos acima compartilham a mesma raiz: são partes do código AS3 do SWF que não são alcançáveis via mudanças no servidor/config. A preservação está "completa" no que é backend; avançar nesses itens exige trabalhar no SWF em si.
