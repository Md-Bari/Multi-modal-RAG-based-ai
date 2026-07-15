from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

# VectorField compatibility for pgvector (PostgreSQL) and SQLite fallback
try:
    from pgvector.django import VectorField
except ImportError:
    class VectorField(models.JSONField):
        def __init__(self, dimensions=None, *args, **kwargs):
            super().__init__(*args, **kwargs)


class Organization(models.Model):
    name = models.CharField(max_length=255)
    plan_tier = models.CharField(max_length=100, default='free')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=255)
    permissions = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, related_name='users', null=True, blank=True)
    sso_provider = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username


class KnowledgeBase(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='knowledge_bases')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_kbs')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50, default='1.0')
    status = models.CharField(max_length=50, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class KBAccess(models.Model):
    kb = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name='access_list')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kb_access_list')
    permission_level = models.CharField(max_length=50)  # read, write, admin
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'KB Access'
        verbose_name_plural = 'KB Accesses'


class RateLimit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rate_limits')
    endpoint = models.CharField(max_length=255)
    requests_count = models.IntegerField(default=0)
    window_start = models.DateTimeField()


class Document(models.Model):
    kb = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name='documents')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')
    source_type = models.CharField(max_length=50)  # file, url
    original_filename = models.CharField(max_length=255)
    storage_url = models.CharField(max_length=500)
    status = models.CharField(max_length=50, default='pending')  # pending, processing, completed, failed
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_filename


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    storage_url = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_text = models.TextField()
    chunk_index = models.IntegerField()
    token_count = models.IntegerField()
    embedding = VectorField(dimensions=768, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProcessingJob(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='processing_jobs')
    job_type = models.CharField(max_length=100)  # ocr, embedding, parsing
    status = models.CharField(max_length=50, default='pending')  # pending, running, completed, failed
    queue_name = models.CharField(max_length=100, default='default')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)


class Conversation(models.Model):
    kb = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name='conversations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=50)  # user, assistant, system
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    token_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role}: {self.content[:30]}..."


class ContextMemory(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='context_memories')
    memory_key = models.CharField(max_length=255)
    memory_value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Context Memory'
        verbose_name_plural = 'Context Memories'


class VoiceRecording(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='voice_recordings')
    audio_url = models.CharField(max_length=500)
    transcript = models.TextField(blank=True)
    duration_seconds = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)


class TokenUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='token_usages')
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='token_usages')
    model_name = models.CharField(max_length=100)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0.000000)
    created_at = models.DateTimeField(auto_now_add=True)


class WebScrapeSource(models.Model):
    kb = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name='scrape_sources')
    url = models.CharField(max_length=500)
    schedule_cron = models.CharField(max_length=100)
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    change_hash = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=50, default='active')


class ScrapeJob(models.Model):
    source = models.ForeignKey(WebScrapeSource, on_delete=models.CASCADE, related_name='scrape_jobs')
    status = models.CharField(max_length=50, default='pending')  # pending, running, completed, failed
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class CacheEntry(models.Model):
    cache_type = models.CharField(max_length=50)  # semantic, response
    cache_key = models.TextField()
    cache_value = models.TextField()
    hit_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Plugin(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='plugins')
    name = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Workflow(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='workflows')
    name = models.CharField(max_length=255)
    definition = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_workflows')
    created_at = models.DateTimeField(auto_now_add=True)
