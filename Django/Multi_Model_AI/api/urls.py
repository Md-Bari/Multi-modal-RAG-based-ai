from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    KnowledgeBaseViewSet, DocumentViewSet, 
    ConversationViewSet, MessageView, AnalyticsView,
    TranscribeView
)

router = DefaultRouter()
router.register(r'knowledge-bases', KnowledgeBaseViewSet, basename='knowledge-base')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'conversations', ConversationViewSet, basename='conversation')

urlpatterns = [
    # Message Routing
    path('conversations/<int:pk>/messages', MessageView.as_view(), name='conversation-messages'),
    
    # Voice Transcription
    path('transcribe', TranscribeView.as_view(), name='transcribe'),
    
    # Analytics
    path('analytics/usage', AnalyticsView.as_view(), name='analytics-usage'),
    
    # ViewSets
    path('', include(router.urls)),
]
