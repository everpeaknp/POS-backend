"""
Signals for setting app
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SiteSettings


@receiver(post_save, sender=SiteSettings)
def update_cloudinary_config(sender, instance, **kwargs):
    """
    Update Cloudinary configuration when SiteSettings is saved.
    This allows dynamic configuration without server restart.
    """
    if instance.use_cloudinary and instance.cloudinary_cloud_name:
        try:
            import cloudinary
            
            cloudinary.config(
                cloud_name=instance.cloudinary_cloud_name,
                api_key=instance.cloudinary_api_key,
                api_secret=instance.cloudinary_api_secret,
                secure=True
            )
            
            # Update Django's default file storage
            from django.conf import settings
            settings.DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
            settings.CLOUDINARY_STORAGE = {
                'CLOUD_NAME': instance.cloudinary_cloud_name,
                'API_KEY': instance.cloudinary_api_key,
                'API_SECRET': instance.cloudinary_api_secret,
            }
        except Exception as e:
            print(f"Failed to update Cloudinary config: {e}")
    else:
        # Switch back to local storage
        try:
            from django.conf import settings
            settings.DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
        except Exception as e:
            print(f"Failed to switch to local storage: {e}")
