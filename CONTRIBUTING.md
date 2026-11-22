# Contributing to Ondos

## Rules
1. **Never commit to `main` directly.** `main` is protected and only changes through Pull Requests.
2. **Work only in your module's folder** (`tilting-platform/`, `glove-controller/`, `vision/`, `auto-controller/`, `control-station/`). Shared code goes in `shared/`, documents in `docs/<module>/`. A change in `shared/` needs the agreement of the modules that use it.
3. **No integration before the instructor approves it.** A module must not import code from another module's folder.
4. **Your git email must be verified on your GitHub account**, or your commits will not be counted. Check with `git config user.email`.
5. Don't commit large binaries (videos, archives, recordings). Share them on Drive. Small model files in `auto-controller/ai/models/` are the exception.
6. **Topic names and message fields come only from `shared/interfaces/`.** Nobody types a topic string by hand.
7. **Tests:** every test of your module has its inputs in `<module>/fixtures/<TEST-ID>/` (inputs + README) and runs with `python run_test.py <TEST-ID>`, printing PASS or FAIL. A module test never needs another module.
8. **Write clean, readable code.** This applies to everyone, and to every AI tool you use: tell it to read this file first, and review what it writes before you commit.
9. **Stay in line with the Module Design Document** (`docs/module-design/`). Code follows the document: its parts, interfaces, requirements and tests. If your work needs something that is not in the document (a new field or topic, a new class, a different behaviour or parameter), do not decide alone. Write it in the issue and tell your module team; if it touches an interface or another module, tell Arif. The document is updated afterwards.

## Clean code

- **One function, one job.** A function does one thing and its name says what. If you need "and" to describe it, split it. Keep functions short enough to read without scrolling.
- **Follow the design document's structure.** Classes, files and function names come from the module's parts table (X.5) and interface tables. Do not invent a different layout; one class per file is the default.
- **Names tell the story.** Clear names instead of comments: `ball_position_mm`, not `p`. Units are part of the name (`tilt_x_deg`, `timeout_ms`).
- **No magic numbers.** Thresholds, timeouts and gains are named constants or variables (from `shared/interfaces/` where they exist), never bare numbers in the middle of code.
- **No copy-paste.** The same logic twice becomes one function. Shared helpers go in `shared/`.
- **Keep it simple.** No clever one-liners, deep nesting or unused code. Return early instead of nesting `if` blocks.
- **Comments explain why, not what.** Add type hints (Python) and types (TypeScript) on public functions.
- **Change only what the task needs.** Do not reformat or rewrite code unrelated to your issue; it makes reviews hard.
- **Reviewers:** a Pull Request that is hard to read is sent back, however well it works.

## Branch names
`<module-folder>/<short-description>`, e.g. `glove-controller/imu-filter`, `vision/ball-detection`, `shared/bus-helper`, `docs/glove-spec`.
After integration is approved: `integration/<what>`, e.g. `integration/glove-platform`.

## Workflow
```bash
git checkout main
git pull
git checkout -b glove-controller/imu-filter
# work, commit small and often
git push -u origin glove-controller/imu-filter
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
2. **Sadece kendi modülünüzün klasöründe çalışın.** Ortak kod `shared/`, dokümanlar `docs/<modül>/` altına. `shared/` değişikliği, onu kullanan modüllerin onayını ister.
3. **Hoca onay vermeden entegrasyon yok.** Bir modül başka modülün klasöründen kod import etmez.
4. **Git e-postanız GitHub hesabınızda doğrulanmış olmalı**, yoksa commit'leriniz sayılmaz. `git config user.email` ile kontrol edin.
5. Büyük dosyaları (video, arşiv, kayıtlar) repoya koymayın, Drive'dan paylaşın. `auto-controller/ai/models/` altındaki küçük model dosyaları istisna.
6. **Topic isimleri ve mesaj alanları sadece `shared/interfaces/`'ten gelir.** Topic string'i elle yazılmaz.
7. **Testler:** modülünüzün her testi `<modül>/fixtures/<TEST-ID>/` altında (girdiler + README) ve `python run_test.py <TEST-ID>` ile çalışır, PASS veya FAIL basar. Modül testi başka bir modüle ihtiyaç duymaz.
8. **Temiz ve okunabilir kod yazın.** Bu herkes için geçerli, kullandığınız her yapay zekâ aracı için de: önce bu dosyayı okumasını söyleyin ve yazdığını commit etmeden önce kendiniz inceleyin.
9. **Modül Tasarım Belgesi'nden (`docs/module-design/`) kopmayın.** Kod belgeyi izler: parçalar, arayüzler, gereksinimler ve testler. İşiniz belgede olmayan bir şey gerektiriyorsa (yeni bir alan ya da topic, yeni bir sınıf, farklı bir davranış ya da parametre) tek başınıza karar vermeyin. Issue'ya yazın ve modül ekibinize söyleyin; bir arayüze ya da başka bir modüle dokunuyorsa Arif'e haber verin. Belge sonradan güncellenir.

**Temiz kod:**
- **Bir fonksiyon, bir iş.** Fonksiyon tek bir şey yapar ve adı bunu söyler. Açıklarken "ve" demeniz gerekiyorsa bölün. Kaydırmadan okunacak kadar kısa tutun.
- **Tasarım belgesinin yapısını izleyin.** Sınıf, dosya ve fonksiyon adları modülün parça tablosundan (X.5) ve arayüz tablolarından gelir. Farklı bir düzen uydurmayın; varsayılan olarak her dosyada bir sınıf.
- **İsimler anlatsın.** Yorum yerine açık isim: `p` değil `ball_position_mm`. Birim isme dahil (`tilt_x_deg`, `timeout_ms`).
- **Sihirli sayı yok.** Eşik, zaman aşımı ve kazançlar isimli sabit ya da değişken olur (varsa `shared/interfaces/`'ten); kodun ortasında çıplak sayı olmaz.
- **Kopyala-yapıştır yok.** Aynı mantık iki yerdeyse tek fonksiyon olur. Ortak yardımcılar `shared/` altına.
- **Basit tutun.** Akıllıca tek satırlıklar, derin iç içe yapı ve kullanılmayan kod olmasın. İç içe `if` yerine erken `return`.
- **Yorum "neden"i anlatır, "ne"yi değil.** Genel fonksiyonlarda tip bilgisi (Python'da type hint, TypeScript'te tipler) olsun.
- **Sadece görevin gerektirdiği şeyi değiştirin.** Issue'nuzla ilgisiz kodu yeniden biçimlendirmeyin ya da yazmayın; incelemeyi zorlaştırır.
- **İnceleyenler:** Okunması zor bir Pull Request, ne kadar iyi çalışırsa çalışsın geri çevrilir.

**Branch adı:** `<modül-klasörü>/<kısa-açıklama>` (ör. `glove-controller/imu-filter`).

**Akış:** `main`'i güncelle → kendi branch'ini aç → küçük ve sık commit at → push → PR aç → 1 onay al → merge.
Branch'ler en fazla birkaç gün yaşasın; her branch'te tek kişi çalışsın; ortak çalışmada commit mesajına `Co-authored-by:` ekleyin.
