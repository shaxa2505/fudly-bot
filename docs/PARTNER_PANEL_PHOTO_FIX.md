# Partner Panel Photo Upload Fix

## 🐛 Problem

Products created through the Partner Panel webapp had the following issues:

1. **Photos not displaying** - uploaded photos were not shown
2. **Products not editable in bot** - couldn't modify products created from Partner Panel
3. **Wrong API flow** - photo file was sent directly to `/products` endpoint

### Root Cause

The Partner Panel was sending the raw photo file to the `/products` endpoint:

```javascript
// ❌ OLD CODE - WRONG
const formData = new FormData();
formData.append('photo', photoFile);  // Raw file
await fetch(`${API}/products`, { body: formData });
```

But the API expected `photo_id` (Telegram file_id string), not a raw file:

```python
# API expects:
photo_id: Optional[str] = Form(None)  # Telegram file_id
```

## ✅ Solution

Implemented two-step photo upload process:

### Step 1: Upload Photo First

```javascript
// 1. Upload photo to get file_id
const photoFormData = new FormData();
photoFormData.append('photo', photoFile);

const photoResponse = await fetch(`${API}/upload-photo`, {
    method: 'POST',
    headers: { 'Authorization': getAuth() },
    body: photoFormData
});

const photoData = await photoResponse.json();
const photoId = photoData.file_id;  // Telegram file_id
```

### Step 2: Create Product with photo_id

```javascript
// 2. Create product with photo_id
const formData = new FormData();
formData.append('title', title);
formData.append('discount_price', price);
formData.append('photo_id', photoId);  // ✅ Use file_id

await fetch(`${API}/products`, {
    method: 'POST',
    body: formData
});
```

## 🎯 Implementation Details

### Upload Photo Endpoint

```python
@router.post("/upload-photo")
async def upload_photo(photo: UploadFile = File(...)):
    """
    1. Receives raw photo file
    2. Sends to Telegram via bot API
    3. Gets file_id from Telegram
    4. Returns file_id to client
    """
    # Send photo to Telegram
    result = await bot_api.send_photo(chat_id, photo)
    file_id = result.photo[-1].file_id
    
    return {"file_id": file_id}
```

### Loading States

Better UX with multi-step feedback:

```javascript
submitBtn.innerHTML = '<div class="spinner-sm"></div> Загрузка фото...';
// ... upload photo ...

submitBtn.innerHTML = '<div class="spinner-sm"></div> Сохранение товара...';
// ... create product ...
```

### Edit Product Support

When editing, show existing photo and preserve `photo_id`:

```javascript
async function editProduct(id) {
    const product = allProducts.find(p => p.id === id);
    
    // Show current photo
    if (product.image) {
        preview.src = product.image;
        preview.classList.remove('hidden');
    }
    
    // Store current photo_id
    modal.dataset.currentPhotoId = product.photo_id;
}

// When saving:
if (newPhotoId) {
    formData.append('photo_id', newPhotoId);
} else if (isEdit && currentPhotoId) {
    formData.append('photo_id', currentPhotoId);  // Keep existing
}
```

## 📊 Before vs After

| Aspect | Before ❌ | After ✅ |
|--------|----------|---------|
| **Photo Display** | Not shown | Shows correctly |
| **Photo Upload** | Direct file | Two-step (file → file_id) |
| **API Call** | Wrong format | Correct format |
| **Edit Support** | Broken | Works perfectly |
| **Error Handling** | Generic | Specific per step |
| **Loading State** | Single | Multi-step feedback |
| **Bot Compatibility** | Incompatible | Fully compatible |

## 🚀 Testing

### Test Case 1: Create Product with Photo

1. Open Partner Panel
2. Click "Добавить товар"
3. Fill form and upload photo
4. Submit
5. **Expected**: Photo appears in product card

### Test Case 2: Edit Product Photo

1. Click edit on existing product
2. See current photo displayed
3. Upload new photo or keep existing
4. Submit
5. **Expected**: Photo updated or kept

### Test Case 3: Create Without Photo

1. Create product without photo
2. **Expected**: Placeholder icon shows (📦)

### Test Case 4: Edit in Bot

1. Create product in Partner Panel
2. Open regular bot
3. Navigate to product management
4. Edit the product
5. **Expected**: Product is fully editable

## 🔧 Technical Notes

### Why Two Steps?

Telegram bot API requires photos to be uploaded through bot's chat:
- Can't store raw files in database
- Need Telegram's `file_id` for consistent access
- Bot can download from Telegram using `file_id`

### Photo Storage Flow

```
User File → Partner Panel → /upload-photo → Telegram API
                                               ↓
                                           file_id
                                               ↓
                          Partner Panel → /products (with file_id)
                                               ↓
                                         Database (photo_id)
                                               ↓
                          Bot/Panel → /photo/{file_id} → Photo URL
```

### Error Handling

```javascript
try {
    // Step 1: Upload photo
    const photoId = await uploadPhoto(file);
} catch (photoError) {
    toast('Ошибка загрузки фото', 'error');
    return;  // Stop here, don't create product
}

try {
    // Step 2: Create product
    await createProduct({ photo_id: photoId });
} catch (productError) {
    toast('Ошибка создания товара', 'error');
    // Photo already uploaded, but product failed
}
```

## 📝 Commit History

- **d9219f6** - `fix: Partner Panel photo upload - upload photo first then create product`
  - Implemented two-step upload
  - Added edit photo support
  - Better loading states
  - Improved error handling

## ✅ Status

**FIXED** - Deployed to production on Dec 17, 2025

All products created via Partner Panel now:
- ✅ Display photos correctly
- ✅ Editable from regular bot
- ✅ Compatible with all bot features
- ✅ Use same data structure as bot-created products

## 🔮 Future Improvements

- [ ] Photo compression before upload (reduce bandwidth)
- [ ] Image cropping/resizing in UI
- [ ] Multiple photo support
- [ ] Photo gallery for reuse
- [ ] Drag & drop upload
- [ ] Progress indicator for large files
