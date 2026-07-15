from rest_framework import serializers
from django.contrib.auth import get_user_model
from core.models import (
    Organization, Role, KnowledgeBase, Document, 
    Conversation, Message, TokenUsage, WebScrapeSource
)

User = get_user_model()

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'plan_tier', 'created_at']


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'permissions']


class UserSerializer(serializers.ModelSerializer):
    org = OrganizationSerializer(read_only=True)
    role = RoleSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'org', 'role', 'sso_provider']


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBase
        fields = ['id', 'org', 'owner', 'name', 'description', 'version', 'status', 'created_at', 'updated_at', 'last_synced_at']
        read_only_fields = ['org', 'owner', 'created_at', 'updated_at', 'last_synced_at']


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'kb', 'uploaded_by', 'source_type', 'original_filename', 'storage_url', 'status', 'metadata', 'created_at']
        read_only_fields = ['kb', 'uploaded_by', 'status', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'role', 'content', 'citations', 'token_count', 'created_at']
        read_only_fields = ['role', 'citations', 'token_count', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'kb', 'user', 'title', 'created_at', 'updated_at', 'messages']
        read_only_fields = ['kb', 'user', 'created_at', 'updated_at']


class TokenUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenUsage
        fields = ['id', 'user', 'conversation', 'model_name', 'input_tokens', 'output_tokens', 'cost', 'created_at']


class WebScrapeSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebScrapeSource
        fields = ['id', 'kb', 'url', 'schedule_cron', 'last_crawled_at', 'change_hash', 'status']
        read_only_fields = ['last_crawled_at', 'change_hash']
