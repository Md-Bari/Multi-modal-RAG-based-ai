from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    LoginView, KnowledgeBaseViewSet, DocumentViewSet, 
    ConversationViewSet, MessageView, AnalyticsView
)

router = DefaultRouter()
router.register(r'knowledge-bases', KnowledgeBaseViewSet, basename='knowledge-base')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'conversations', ConversationViewSet, basename='conversation')

urlpatterns = [
    # Auth
    path('auth/login', LoginView.as_view(), name='token_obtain_pair'),
    
    # Message Routing
    path('conversations/<int:pk>/messages', MessageView.as_view(), name='conversation-messages'),
    
    # Analytics
    path('analytics/usage', AnalyticsView.as_view(), name='analytics-usage'),
    
    # ViewSets
    path('', include(router.urls)),
]
