# 文件上传/下载安全规范

> 适用：Spring Boot 3，单体 + 微服务

---

## 一、文件大小限制

### 1.1 全局限制

```yaml
# application.yml
spring:
  servlet:
    multipart:
      max-file-size: 10MB        # 单个文件最大
      max-request-size: 20MB     # 单次请求总大小
```

### 1.2 接口级限制

```java
@PostMapping("/upload")
public Result<FileVO> upload(
        @RequestPart("file") @Parameter(description = "上传文件") MultipartFile file) {
    if (file.getSize() > 5 * 1024 * 1024) {
        throw new BusinessException(BusinessErrorEnum.FILE_SIZE_EXCEED);
    }
    // ...
}
```

| 规则 | 说明 |
|------|------|
| 全局配置 `max-file-size` / `max-request-size` | 防止恶意大文件攻击 |
| 接口级额外限制 | 不同接口有不同的合理上限（头像 2MB、附件 10MB） |
| 前后端双重校验 | 前端拦截体验好，后端校验是安全底线 |

---

## 二、文件类型白名单

### 2.1 禁止黑名单校验

```java
// ❌ 禁止：黑名单（永远赶不上攻击者）
if (ext.equals("exe") || ext.equals("sh")) { ... }
```

### 2.2 必须白名单

```java
// ✅ 白名单：只允许已知安全类型
private static final Set<String> ALLOWED_EXTENSIONS =
    Set.of("jpg", "jpeg", "png", "gif", "pdf", "doc", "docx", "xls", "xlsx");

private static final Map<String, String> ALLOWED_CONTENT_TYPES = Map.of(
    "jpg", "image/jpeg",
    "jpeg", "image/jpeg",
    "png", "image/png",
    "gif", "image/gif",
    "pdf", "application/pdf"
);

public void validateFile(MultipartFile file) {
    // 1. 校验 Content-Type（浏览器给的，可能被伪造）
    String contentType = file.getContentType();

    // 2. 校验扩展名（从原始文件名提取）
    String originalName = file.getOriginalFilename();
    String ext = FilenameUtils.getExtension(originalName).toLowerCase();

    // 3. 魔数校验（可信度最高）
    String magic = detectMagicNumber(file.getInputStream());
}
```

| 校验层级 | 可信度 | 说明 |
|---------|:--:|------|
| Content-Type | ⭐ | 浏览器上报，可被篡改 |
| 文件扩展名 | ⭐⭐ | 从文件名提取，可被伪造成 `shell.php.jpg` |
| 魔数（文件头） | ⭐⭐⭐⭐ | 读前几个字节判断真实类型，最可靠 |

### 2.3 魔数校验实现

```java
private String detectMagicNumber(InputStream is) throws IOException {
    byte[] header = new byte[8];
    int read = is.read(header);
    if (read < 4) return "unknown";

    // PNG
    if (header[0] == (byte) 0x89 && header[1] == 'P' && header[2] == 'N' && header[3] == 'G') {
        return "png";
    }
    // JPEG
    if (header[0] == (byte) 0xFF && header[1] == (byte) 0xD8) {
        return "jpeg";
    }
    // GIF
    if (header[0] == 'G' && header[1] == 'I' && header[2] == 'F') {
        return "gif";
    }
    // PDF
    if (header[0] == '%' && header[1] == 'P' && header[2] == 'D' && header[3] == 'F') {
        return "pdf";
    }
    return "unknown";
}
```

---

## 三、路径遍历防护

### 3.1 文件命名

```java
// ❌ 禁止：直接使用用户上传的文件名
String fileName = file.getOriginalFilename();  // 可能包含 ../ 或 /
Files.write(Paths.get("/uploads", fileName), bytes);

// ✅ 服务端生成文件名（UUID + 原始扩展名）
String fileName = UUID.randomUUID() + "." + FilenameUtils.getExtension(file.getOriginalFilename());
Path targetPath = Paths.get(baseDir, fileName);
// 安全检查：确保最终路径在 baseDir 内
if (!targetPath.normalize().startsWith(basePath)) {
    throw new BusinessException(BusinessErrorEnum.FILE_UPLOAD_FAILED);
}
Files.write(targetPath, bytes);
```

### 3.2 规则

| 规则 | 说明 |
|------|------|
| 文件名由服务端生成 | UUID/雪花ID + 保留扩展名，不接受用户输入 |
| 存储路径规范化后再校验 | 调用 `Path.normalize()` + `startsWith(basePath)` |
| 禁止拼接用户输入到路径 | 不使用 `originalFilename` 做路径组成部分 |
| 原始文件名存入数据库 | 下载时用原始文件名展示，但存储和访问只用生成名 |

---

## 四、存储策略

### 4.1 本地存储

```java
@ConfigurationProperties(prefix = "app.file")
public class FileStorageConfig {
    /** 文件存储根目录，通过环境变量注入 */
    private String basePath = "/data/uploads";
}
```

| 规则 | 说明 |
|------|------|
| 存储路径通过配置管理 | 不硬编码路径 |
| 不放在 `static/` 或 `resources/` | 这些目录下的文件可被直接 URL 访问，安全风险 |
| 按日期分目录 | 如 `/data/uploads/2026/06/04/xxx.pdf`，避免单目录文件过多 |

### 4.2 对象存储（推荐）

生产环境推荐使用 MinIO / OSS / S3，不依赖服务器本地磁盘：

```java
// 使用 Spring Cloud Alibaba OSS 或 MinIO SDK
// 上传后返回 URL，不返回文件流
```

### 4.3 存储路径不在 static 下

```java
// ❌ 禁止：上传到 static 目录
Path path = Paths.get("src/main/resources/static/uploads", fileName);

// ✅ 上传到外部存储目录
Path path = Paths.get("/data/uploads", dateDir, fileName);
```

---

## 五、下载安全

### 5.1 路径参数校验

```java
@GetMapping("/download/{fileId}")
public ResponseEntity<Resource> download(@PathVariable Long fileId) {
    FileEntity file = fileService.getById(fileId);
    if (file == null) {
        throw new BusinessException(BusinessErrorEnum.FILE_NOT_FOUND);
    }

    Path filePath = Paths.get(baseDir, file.getStoredPath());
    Resource resource = new UrlResource(filePath.toUri());
    if (!resource.exists()) {
        throw new BusinessException(BusinessErrorEnum.FILE_NOT_FOUND);
    }

    return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=\"" + URLEncoder.encode(file.getOriginalName(), StandardCharsets.UTF_8) + "\"")
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(resource);
}
```

### 5.2 规则

| 规则 | 说明 |
|------|------|
| 下载通过 fileId 查找 | 不暴露服务器文件路径给前端 |
| 下载文件名 URLEncode | 中文文件名不乱码 |
| 不提供目录遍历下载 | 禁止 `/download?path=../etc/passwd` 这类参数 |
| Content-Type 设 `APPLICATION_OCTET_STREAM` | 强制下载而非浏览器预览（防止 XSS） |

---

## 六、禁止事项

| 禁止 | 原因 |
|------|------|
| 使用用户上传的原始文件名做存储路径 | 路径遍历攻击（`../../../etc/passwd`） |
| 文件类型用黑名单校验 | 黑名单永远追不上攻击者 |
| 上传文件存放到 `static/` 或 `resources/` | 可直接通过 URL 访问执行 |
| 不限制文件大小 | 恶意大文件打满磁盘 |
| 下载接口路径参数不校验 | 路径遍历，可读取服务器任意文件 |
| 前端可上传 HTML/SVG 文件 | SVG 可嵌入 `<script>`，HTML 可直接执行 XSS |

---

## 七、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../quality/error-code-reference.md` | `FILE_NOT_FOUND`、`FILE_SIZE_EXCEED`、`FILE_FORMAT_UNSUPPORTED` |
| `config-guide.md` | 存储路径通过 `@ConfigurationProperties` 管理 |
| `../layered/controller-guide.md` | 上传接口用 POST + `@RequestPart` |
