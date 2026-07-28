# PYTHON CLEAN CODE, PEP 8 VE VS CODE GELİŞTİRME TALİMATI

> **ELI5:** Bu dosya “kod nasıl yazılmalı?” kural kitabıdır; özellik durum raporu
> değildir. Güncel kalite komutu ve sonuçları kök `README.md` içindedir.

Bu projede yazılan, düzenlenen veya yeniden yapılandırılan tüm Python kodlarında aşağıdaki kuralları zorunlu olarak uygula.

## 1. Temel Kodlama İlkeleri

Kodlar:

* Yalın, okunabilir, anlaşılır ve sürdürülebilir olmalıdır.
* PEP 8 kodlama standardına uygun yazılmalıdır.
* PEP 257 docstring standardına uyulmalıdır.
* KISS, DRY, YAGNI ve SOLID prensipleri dengeli biçimde uygulanmalıdır.
* Gereksiz soyutlama, aşırı mühendislik ve karmaşık tasarım kalıplarından kaçınılmalıdır.
* Mevcut problemi çözen en basit, güvenilir ve test edilebilir çözüm tercih edilmelidir.
* Tekrarlanan kodlar ortak fonksiyon, sınıf veya modüllere ayrılmalıdır.
* Kullanılmayan kod, import, değişken, fonksiyon ve yorum bırakılmamalıdır.
* Geçici çözümler, sahte veriler, placeholder kodlar ve sessizce hata yutan yapılar kullanılmamalıdır.

## 2. Kod Yapısı

Her fonksiyon ve sınıf yalnızca tek bir temel sorumluluğa sahip olmalıdır.

Aşağıdaki sınırlar hedeflenmelidir:

* Fonksiyonlar tercihen 30 satırdan kısa olmalıdır.
* Sınıflar gereksiz şekilde büyütülmemelidir.
* İç içe koşul ve döngü derinliği mümkün olduğunca üç seviyeyi aşmamalıdır.
* Uzun fonksiyonlar anlamlı alt fonksiyonlara ayrılmalıdır.
* Global değişken kullanımından kaçınılmalıdır.
* Sabit değerler `UPPER_CASE` isimli sabitler olarak tanımlanmalıdır.
* Dosya yolları için `pathlib.Path` kullanılmalıdır.
* Kaynak yönetimi için `with` context manager tercih edilmelidir.
* Veri taşıma amacıyla uygun olduğunda `dataclass`, `TypedDict`, `Enum` veya Pydantic modelleri kullanılmalıdır.
* İş mantığı; kullanıcı arayüzü, API, dosya sistemi ve veri erişimi katmanlarından ayrılmalıdır.

## 3. İsimlendirme Kuralları

İsimler açık, açıklayıcı ve amaca yönelik olmalıdır.

* Değişken ve fonksiyonlar: `snake_case`
* Sınıflar: `PascalCase`
* Sabitler: `UPPER_CASE`
* Özel kullanım üyeleri: `_leading_underscore`
* Python dosyaları: `snake_case.py`

Şu tür belirsiz isimlerden kaçın:

* `data`
* `temp`
* `value`
* `result`
* `item`
* `obj`
* `x`
* `foo`
* `bar`

Bunların yerine bağlama özgü isimler kullan:

```python
validated_orders
monthly_incident_count
configuration_path
risk_assessment_result
```

Tek harfli değişkenlere yalnızca kısa ve açık döngülerde izin ver.

## 4. Tip Güvenliği

Tüm yeni veya değiştirilen fonksiyonlarda type hint kullan.

```python
def calculate_total_cost(
    unit_price: float,
    quantity: int,
) -> float:
    return unit_price * quantity
```

Aşağıdaki kuralları uygula:

* Fonksiyon parametrelerini ve dönüş değerlerini tiple.
* Gereksiz `Any` kullanımından kaçın.
* `Optional` durumlarını açıkça ele al.
* Karmaşık tipler için type alias oluştur.
* Mümkün olduğunda `list[str]`, `dict[str, int]` gibi modern Python tiplerini kullan.
* Dönüş tipi bulunmayan fonksiyonlarda `-> None` belirt.
* Tip kontrolünde Pyright veya MyPy ile uyumlu kod yaz.

## 5. Fonksiyon Tasarımı

Fonksiyonlar:

* Tek bir işi yapmalıdır.
* Açık girdi ve çıktı üretmelidir.
* Gizli yan etkiler oluşturmamalıdır.
* Gereksiz sayıda parametre almamalıdır.
* Boolean parametrelerle birden fazla davranış yüklenmemelidir.
* Mümkün olduğunda saf fonksiyon olarak tasarlanmalıdır.
* Erken dönüş kullanılarak karmaşık iç içe koşullar azaltılmalıdır.

Tercih edilen yapı:

```python
def process_record(record: Record) -> ProcessedRecord:
    if not record.is_valid:
        raise InvalidRecordError("Record validation failed.")

    normalized_record = normalize_record(record)
    return transform_record(normalized_record)
```

Kaçınılması gereken yapı:

```python
def process_record(record, mode=False, flag=True):
    if record:
        if mode:
            if flag:
                ...
```

## 6. Hata Yönetimi

* `except Exception:` yalnızca zorunlu üst seviye sınırlarında kullanılmalıdır.
* Çıplak `except:` kullanılmamalıdır.
* Hatalar sessizce bastırılmamalıdır.
* Beklenen hata türleri ayrı ayrı yakalanmalıdır.
* Anlamlı özel exception sınıfları oluşturulmalıdır.
* Hata mesajları açık, bağlamsal ve işlem yapılabilir olmalıdır.
* Hata oluştuğunda gerekli bağlam loglanmalı, ancak parola, token veya kişisel veri kaydedilmemelidir.
* Hatanın kaynağını gizleyen gereksiz exception wrapping yapılmamalıdır.

```python
try:
    configuration = load_configuration(configuration_path)
except FileNotFoundError as exc:
    raise ConfigurationError(
        f"Configuration file not found: {configuration_path}"
    ) from exc
```

## 7. Loglama

Üretim kodunda `print()` yerine standart `logging` modülünü kullan.

```python
import logging

logger = logging.getLogger(__name__)
```

Log seviyeleri doğru kullanılmalıdır:

* `DEBUG`: Teknik teşhis bilgileri
* `INFO`: Normal işlem akışı
* `WARNING`: İşlem devam edebilir ancak dikkat gerektirir
* `ERROR`: İşlem başarısız olmuştur
* `CRITICAL`: Sistem çalışmasını etkileyen ciddi hata

Parola, API anahtarı, access token, kişisel veri veya hassas bilgiler loglanmamalıdır.

## 8. Dokümantasyon ve Yorumlar

Docstring şu durumlarda kullanılmalıdır:

* Public fonksiyonlar
* Public sınıflar
* Karmaşık modüller
* Anlaşılması zor iş kuralları
* Harici kullanıma açık API bileşenleri

Docstring, kodun ne yaptığını tekrar etmek yerine amacı, parametreleri, dönüş değerini ve önemli hata durumlarını açıklamalıdır.

```python
def calculate_risk_score(
    likelihood: int,
    severity: int,
) -> int:
    """Calculate the risk score from likelihood and severity.

    Args:
        likelihood: Probability rating between 1 and 5.
        severity: Consequence rating between 1 and 5.

    Returns:
        Calculated risk score.

    Raises:
        ValueError: If either rating is outside the accepted range.
    """
```

Yorumlar:

* Kodun ne yaptığını değil, neden o şekilde yapıldığını açıklamalıdır.
* Güncelliğini kaybetmiş veya gereksiz yorumlar bırakılmamalıdır.
* Yorumlanmış eski kod saklanmamalıdır; sürüm geçmişi Git üzerinden yönetilmelidir.

## 9. Import Düzeni

Importlar aşağıdaki sırada tutulmalıdır:

1. Python standart kütüphaneleri
2. Üçüncü taraf paketler
3. Proje içi modüller

Gruplar arasında bir boş satır bulunmalıdır.

Wildcard import kullanılmamalıdır:

```python
from module import *
```

Döngüsel importlardan kaçınılmalıdır. Import sıralaması Ruff veya isort ile doğrulanmalıdır.

## 10. Güvenlik

* Parola, API anahtarı, token ve bağlantı bilgileri kaynak koda yazılmamalıdır.
* Hassas ayarlar environment variable veya güvenli secret yönetimi üzerinden alınmalıdır.
* Kullanıcı girdileri doğrulanmalıdır.
* Dosya yolları kontrol edilmeden kullanılmamalıdır.
* SQL sorgularında parametrik sorgular kullanılmalıdır.
* `eval()` ve `exec()` kullanılmamalıdır.
* Shell komutlarında kullanıcı girdisi doğrudan birleştirilmemelidir.
* `subprocess` kullanımında `shell=True` varsayılan olarak kullanılmamalıdır.
* Güvenilir olmayan pickle dosyaları yüklenmemelidir.
* Loglarda ve hata mesajlarında hassas bilgiler açığa çıkarılmamalıdır.

## 11. Test Edilebilirlik

Yeni işlevler için uygun testler hazırlanmalıdır.

Testlerde:

* `pytest` kullanılmalıdır.
* Normal senaryo test edilmelidir.
* Sınır değerler test edilmelidir.
* Geçersiz girdiler test edilmelidir.
* Beklenen exception durumları test edilmelidir.
* Dosya sistemi, ağ ve harici servisler gerektiğinde mock edilmelidir.
* Testler birbirinden bağımsız olmalıdır.
* Test sonucu çalışma sırasına bağlı olmamalıdır.
* Bir hata düzeltildiğinde mümkünse regresyon testi eklenmelidir.

Test isimleri davranışı açıklamalıdır:

```python
def test_calculate_risk_score_rejects_out_of_range_likelihood() -> None:
    ...
```

## 12. Kod Biçimlendirme ve Kalite Araçları

Kodları aşağıdaki araçlarla uyumlu oluştur:

* Ruff: lint, import düzeni ve temel kod kalitesi
* Black veya Ruff formatter: otomatik biçimlendirme
* Pyright veya MyPy: statik tip kontrolü
* Pytest: testler
* Bandit: temel güvenlik kontrolü
* pre-commit: commit öncesi kalite kontrolleri

Önerilen kontrol sırası:

```bash
ruff format .
ruff check . --fix
pytest
pyright
```

Kod kalitesi kontrollerini geçmeden görevi tamamlanmış kabul etme.

## 13. PEP 8 Biçimlendirme Kuralları

* Satır uzunluğunu tercihen 88 karakterle sınırla.
* Operatörlerin çevresinde uygun boşluk bırak.
* Fonksiyon ve sınıflar arasında PEP 8’e uygun boş satır kullan.
* Çok uzun ifadeleri parantez içinde böl.
* Backslash ile satır devamından kaçın.
* Aynı satırda birden fazla işlem yazma.
* Gereksiz noktalı virgül kullanma.
* Boolean karşılaştırmalarında `== True` veya `== False` kullanma.
* Boş koleksiyon kontrolünde `len(collection) == 0` yerine doğrudan doğruluk kontrolü kullan.

```python
if not records:
    return []
```

## 14. Pythonic Kodlama

Python’un standart ve okunabilir yapılarını tercih et:

* List, dict ve set comprehension yalnızca okunabilir kaldığı sürece kullanılmalıdır.
* Karmaşık comprehension ifadeleri normal döngülere dönüştürülmelidir.
* `enumerate()` ve `zip()` uygun yerlerde kullanılmalıdır.
* Üyelik kontrolünde listeler yerine gerektiğinde set kullanılmalıdır.
* Kaynak yönetiminde context manager kullanılmalıdır.
* Manuel indeks takibi yapılmamalıdır.
* Mutable default argument kullanılmamalıdır.

Yanlış:

```python
def add_record(record: Record, records: list[Record] = []) -> None:
    records.append(record)
```

Doğru:

```python
def add_record(
    record: Record,
    records: list[Record] | None = None,
) -> list[Record]:
    target_records = records if records is not None else []
    target_records.append(record)
    return target_records
```

## 15. Yapılandırma ve Sabitler

* Ortama bağlı değerleri kod içine gömme.
* Ayarları merkezi bir configuration katmanında yönet.
* Magic number ve magic string kullanımından kaçın.
* Birimler değişken adında veya veri modelinde açıkça belirtilmelidir.

```python
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRY_COUNT = 3
```

## 16. Asenkron Kod

* Yalnızca gerçek I/O işlemlerinde `asyncio` kullan.
* CPU ağırlıklı işlemler için gereksiz `async` kullanımından kaçın.
* Async fonksiyon içinde bloklayan senkron I/O çalıştırma.
* Task, timeout ve cancellation durumlarını açıkça yönet.
* Eş zamanlılık kontrolü için gerektiğinde semaphore kullan.
* Arka planda başlatılan taskları takip edilmeden bırakma.

## 17. Mevcut Kodu Düzenleme Kuralları

Mevcut bir dosyada değişiklik yaparken:

1. Önce mevcut kodu ve bağımlılıklarını incele.
2. Projenin mevcut mimarisini ve isimlendirme düzenini koru.
3. Yalnızca gerekli bölümleri değiştir.
4. İlgisiz dosyalarda toplu biçimlendirme veya refactor yapma.
5. Mevcut API davranışını gerekmedikçe bozma.
6. Geriye dönük uyumsuz değişiklikleri açıkça belirt.
7. Aynı işlevi yapan ikinci bir mekanizma oluşturma.
8. Yeni kod eklemeden önce mevcut yardımcı fonksiyonları araştır.
9. Kod tekrarını azalt, ancak aşırı soyutlama oluşturma.
10. Değişiklik sonrasında lint, type check ve testleri çalıştır.

## 18. Kod Üretim Süreci

Her kodlama görevinde şu sırayı izle:

1. Talebi ve kabul kriterlerini analiz et.
2. İlgili dosyaları ve mevcut kod akışını incele.
3. En küçük güvenli değişiklik planını belirle.
4. Yalın ve PEP 8 uyumlu kodu uygula.
5. Gereksiz kodları ve importları temizle.
6. Hata durumlarını ele al.
7. Type hint ve gerekli docstringleri ekle.
8. Testleri ekle veya güncelle.
9. Formatter, linter, type checker ve testleri çalıştır.
10. Yapılan değişiklikleri kısa ve doğrulanabilir şekilde raporla.

## 19. Çıktı Formatı

Bir görev tamamlandığında şu bilgileri ver:

### Sonuç

Görevin tamamlanıp tamamlanmadığını açıkça belirt.

### Değiştirilen Dosyalar

Her dosya için yapılan değişikliği bir cümleyle açıkla.

### Kalite Kontrolleri

Aşağıdaki kontrollerin durumunu bildir:

* Ruff format
* Ruff lint
* Type check
* Pytest
* Güvenlik kontrolü

Çalıştırılmayan bir kontrol varsa çalıştırılmış gibi davranma. Neden çalıştırılamadığını açıkça belirt.

### Önemli Teknik Notlar

Yalnızca karar verilmesi gereken, geriye dönük uyumsuzluk oluşturan veya risk taşıyan hususları belirt.

## 20. Nihai Karar Kuralı

Kod şu kriterlerin tamamını karşılamıyorsa görevi bitmiş sayma:

* Sözdizimi hatası bulunmuyor.
* PEP 8 uyumlu.
* Formatter ve lint kontrollerinden geçiyor.
* Kullanılmayan import veya ölü kod bulunmuyor.
* Type hintler yeterli.
* Hatalar kontrollü şekilde ele alınıyor.
* Hassas bilgi içermiyor.
* Mevcut proje mimarisiyle uyumlu.
* Test edilebilir.
* Gereksiz karmaşıklık içermiyor.
* Görevin kabul kriterlerini karşılıyor.

Öncelik sırası:

1. Doğruluk
2. Güvenlik
3. Veri bütünlüğü
4. Okunabilirlik
5. Test edilebilirlik
6. Sürdürülebilirlik
7. Performans
8. Kod kısalığı

Kısa kod uğruna doğruluk, okunabilirlik veya güvenlikten ödün verme.
