# File Upload Handling

Django-fileindex provides several utilities to simplify file upload handling and automatic IndexedFile creation.

## Quick Start

### Using IndexedFileField in Forms

The simplest way to handle file uploads with automatic IndexedFile creation:

```python
from django import forms
from fileindex import IndexedFileField

class DocumentUploadForm(forms.Form):
    document = IndexedFileField(
        label="Upload Document",
        allowed_extensions=['.pdf', '.doc', '.docx'],
        max_file_size=10 * 1024 * 1024,  # 10MB
        required=True
    )
    
    def save(self):
        # The field returns an IndexedFile instance
        indexed_file = self.cleaned_data['document']
        # Use the indexed_file as needed
        return indexed_file
```

### Using IndexedFileModelForm

For ModelForms that need to handle file uploads:

```python
from fileindex import IndexedFileModelForm
from myapp.models import Document

class DocumentForm(IndexedFileModelForm):
    class Meta:
        model = Document
        fields = ['title', 'description']
    
    # Specify which field on the model stores the IndexedFile
    indexed_file_field_name = 'file'
    upload_field_name = 'upload_file'  # The form field name
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize the upload field if needed
        self.fields['upload_file'].help_text = "Upload a PDF document"
```

## Form Fields

### IndexedFileField

A form field that automatically creates IndexedFile entries from uploaded files.

**Parameters:**
- `allowed_extensions`: List of allowed file extensions (e.g., `['.jpg', '.png']`)
- `max_file_size`: Maximum file size in bytes
- `path_prefix`: Prefix for temporary file storage (default: `'uploads/temp'`)

**Example:**

```python
from fileindex import IndexedFileField

class ImageUploadForm(forms.Form):
    image = IndexedFileField(
        allowed_extensions=['.jpg', '.jpeg', '.png', '.gif'],
        max_file_size=5 * 1024 * 1024,  # 5MB
        path_prefix='images/temp'
    )
```

### MultipleIndexedFilesField

Handle multiple file uploads at once:

```python
from fileindex import MultipleIndexedFilesField

class GalleryForm(forms.Form):
    images = MultipleIndexedFilesField(
        widget=forms.ClearableFileInput(attrs={'multiple': True}),
        allowed_extensions=['.jpg', '.png'],
        max_file_size=5 * 1024 * 1024,  # Per file
        max_files=10  # Maximum 10 files
    )
```

## Form Mixins

### IndexedFileUploadMixin

Add file upload capability to any ModelForm:

```python
from fileindex import IndexedFileUploadMixin
from django import forms

class ProductImageForm(IndexedFileUploadMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['alt_text', 'caption']
    
    indexed_file_field_name = 'image'  # Model field that stores IndexedFile
    upload_field_name = 'image_upload'  # Form field for upload
    upload_path_prefix = 'products/images/temp'
```

### MultipleIndexedFilesFormMixin

Handle multiple file uploads in a form:

```python
from fileindex import MultipleIndexedFilesFormMixin

class BatchUploadForm(MultipleIndexedFilesFormMixin, forms.Form):
    category = forms.CharField(max_length=100)
    
    multiple_files_field_name = 'files'
    upload_path_prefix = 'batch/temp'
    
    def save_indexed_files(self, indexed_files):
        # Custom logic to handle the uploaded files
        for indexed_file in indexed_files:
            Document.objects.create(
                category=self.cleaned_data['category'],
                file=indexed_file
            )
```

## Utility Functions

### create_indexed_file_from_upload

Create an IndexedFile from a Django UploadedFile:

```python
from fileindex import create_indexed_file_from_upload
from django.core.files.uploadedfile import UploadedFile

def handle_upload(uploaded_file: UploadedFile):
    indexed_file, created = create_indexed_file_from_upload(
        uploaded_file,
        path_prefix='uploads/documents',
        cleanup_on_error=True
    )
    return indexed_file
```

### validate_image_upload

Validate image files before processing:

```python
from fileindex import validate_image_upload

def validate_avatar(uploaded_file):
    validate_image_upload(
        uploaded_file,
        allowed_formats=['JPEG', 'PNG'],
        max_size=2 * 1024 * 1024,  # 2MB
        min_dimensions=(100, 100),  # At least 100x100
        max_dimensions=(2000, 2000)  # At most 2000x2000
    )
```

### create_indexed_files_batch

Process multiple files at once:

```python
from fileindex import create_indexed_files_batch

def handle_batch_upload(files):
    indexed_files = create_indexed_files_batch(
        files,
        path_prefix='batch/uploads',
        atomic=True  # Use database transaction
    )
    return indexed_files
```

### get_upload_path_for_model

Generate consistent upload paths:

```python
from fileindex import get_upload_path_for_model

class Document(models.Model):
    def upload_to(self, filename):
        return get_upload_path_for_model(
            self, 
            filename, 
            base_path='documents'
        )
        # Returns: 'documents/app_label/document/123/filename.pdf'
```

## Django Admin Integration

### Simple Upload Inline

```python
from django.contrib import admin
from fileindex import IndexedFileField

class DocumentInline(admin.StackedInline):
    model = Document
    extra = 1
    
    def get_formset(self, request, obj=None, **kwargs):
        from django import forms
        
        class DocumentForm(forms.ModelForm):
            upload = IndexedFileField(
                allowed_extensions=['.pdf'],
                max_file_size=10 * 1024 * 1024
            )
            
            class Meta:
                model = Document
                fields = ['title']
            
            def save(self, commit=True):
                instance = super().save(commit=False)
                if self.cleaned_data.get('upload'):
                    instance.file = self.cleaned_data['upload']
                if commit:
                    instance.save()
                return instance
        
        kwargs['form'] = DocumentForm
        return super().get_formset(request, obj, **kwargs)
```

### Advanced Admin with Validation

```python
from django.contrib import admin
from fileindex import IndexedFileField, validate_image_upload

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    
    def get_formset(self, request, obj=None, **kwargs):
        class ProductImageForm(forms.ModelForm):
            image_upload = IndexedFileField(
                label="Product Image",
                allowed_extensions=['.jpg', '.jpeg', '.png'],
                max_file_size=5 * 1024 * 1024,
                required=False
            )
            
            class Meta:
                model = ProductImage
                fields = ['alt_text', 'is_primary']
            
            def clean_image_upload(self):
                file = self.cleaned_data.get('image_upload')
                if file:
                    # Additional validation
                    validate_image_upload(
                        file.file,  # Access the actual file
                        min_dimensions=(400, 400),
                        max_dimensions=(4000, 4000)
                    )
                return file
            
            def save(self, commit=True):
                instance = super().save(commit=False)
                if self.cleaned_data.get('image_upload'):
                    instance.image = self.cleaned_data['image_upload']
                if commit:
                    instance.save()
                return instance
        
        kwargs['form'] = ProductImageForm
        return super().get_formset(request, obj, **kwargs)
```

## Best Practices

1. **Always validate file types and sizes** to prevent abuse
2. **Use transactions** when creating multiple related objects
3. **Clean up temporary files** on errors using the provided utilities
4. **Set appropriate path prefixes** to organize uploaded files
5. **Use the mixins** instead of writing custom upload logic
6. **Handle errors gracefully** and provide user-friendly messages

## Error Handling

All upload utilities properly clean up temporary files on errors:

```python
from django.core.exceptions import ValidationError
from fileindex import create_indexed_file_from_upload

try:
    indexed_file, created = create_indexed_file_from_upload(
        uploaded_file,
        cleanup_on_error=True  # Default is True
    )
except ValidationError as e:
    # Handle validation errors
    print(f"Upload failed: {e}")
except Exception as e:
    # Handle other errors
    print(f"Unexpected error: {e}")
```

## Migration from Manual Upload Handling

If you have existing code that manually handles uploads:

### Before (Manual Handling)
```python
# Old way - manual handling
def save(self, commit=True):
    instance = super().save(commit=False)
    if self.cleaned_data.get('file'):
        file = self.cleaned_data['file']
        # Manual save and IndexedFile creation
        path = default_storage.save(f'uploads/{file.name}', file)
        full_path = default_storage.path(path)
        indexed_file, _ = IndexedFile.objects.get_or_create_from_file(full_path)
        instance.file = indexed_file
        default_storage.delete(path)  # Cleanup
    if commit:
        instance.save()
    return instance
```

### After (Using IndexedFileField)
```python
# New way - using IndexedFileField
upload_file = IndexedFileField(
    path_prefix='uploads',
    max_file_size=10 * 1024 * 1024
)

def save(self, commit=True):
    instance = super().save(commit=False)
    if self.cleaned_data.get('upload_file'):
        instance.file = self.cleaned_data['upload_file']  # Already an IndexedFile
    if commit:
        instance.save()
    return instance
```

The new approach is cleaner, handles errors better, and includes automatic cleanup.