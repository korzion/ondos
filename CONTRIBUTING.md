# Contributing to Ondos

## Rules
1. **Never commit to `main` directly.** `main` is protected and only changes through Pull Requests.
2. **Work only in your module's folder** (`platform/`, `glove/`, `vision/`, `simulator/`, `path-planning/`, `ai/`, `control-station/`). Shared code goes in `shared/`, documents in `docs/<module>/`.
3. **No integration before the instructor approves it.** A module must not import code from another module's folder.
4. **Your git email must be verified on your GitHub account**, or your commits will not be counted. Check with `git config user.email`.
5. Don't commit large binaries (videos, Unity builds, archives). Share them on Drive.

## Branch names
`<module>/<short-description>`, e.g. `glove/flex-sensor-read`, `vision/ball-detection`, `docs/glove-spec`.
After integration is approved: `integration/<what>`, e.g. `integration/glove-platform`.

## Workflow
```bash
git checkout main
git pull
git checkout -b glove/flex-sensor-read
# work, commit small and often
git push -u origin glove/flex-sensor-read
```
Then open a Pull Request on GitHub, get **1 approval** (from your module team if possible) and click **Merge pull request**. The branch is deleted automatically.

- Keep branches short-lived (a few days at most). Merge working pieces early.
- If your branch lives longer, update it with `git pull origin main`.
- One person per branch.
- When you work with someone, add `Co-authored-by: Name <email>` to the commit message.
- Integration PRs need one approval from each module involved.

## Milestone tags
`v0.2-module-docs` → `v0.3-module-demo` → `v1.0-final`

---

# Katkı Kuralları (Türkçe)

1. **`main`'e asla doğrudan commit atmayın.** `main` korumalıdır, sadece Pull Request ile değişir.
2. **Sadece kendi modülünüzün klasöründe çalışın.** Ortak kod `shared/`, dokümanlar `docs/<modül>/` altına.
3. **Hoca onay vermeden entegrasyon yok.** Bir modül başka modülün klasöründen kod import etmez.
4. **Git e-postanız GitHub hesabınızda doğrulanmış olmalı**, yoksa commit'leriniz sayılmaz. `git config user.email` ile kontrol edin.
5. Büyük dosyaları (video, Unity build, arşiv) repoya koymayın, Drive'dan paylaşın.

**Branch adı:** `<modül>/<kısa-açıklama>` (ör. `glove/flex-sensor-read`).

**Akış:** `main`'i güncelle → kendi branch'ini aç → küçük ve sık commit at → push → PR aç → 1 onay al → merge.
Branch'ler en fazla birkaç gün yaşasın; her branch'te tek kişi çalışsın; ortak çalışmada commit mesajına `Co-authored-by:` ekleyin.
