import pytest
from unittest.mock import Mock, patch
from bubbleviews.analysis.news_analyzer import NewsAnalyzer
from bubbleviews.models import NewsItem

@pytest.fixture
def mock_reddit_client():
    client = Mock()
    client.subreddits = ['news', 'worldnews']
    return client

@pytest.fixture
def news_analyzer(mock_reddit_client):
    return NewsAnalyzer(mock_reddit_client)

@pytest.mark.asyncio
async def test_get_top_news(news_analyzer, mock_reddit_client):
    # Mock data
    mock_posts = [
        {
            'title': 'Test News 1',
            'url': 'http://test1.com',
            'score': 100,
            'upvote_ratio': 0.8,
            'num_comments': 50,
            'created_utc': 1600000000
        },
        {
            'title': 'Test News 2',
            'url': 'http://test2.com',
            'score': 200,
            'upvote_ratio': 0.9,
            'num_comments': 75,
            'created_utc': 1600000100
        }
    ]
    
    mock_reddit_client.get_hot_posts.return_value = mock_posts
    
    # Get results
    results = await news_analyzer.get_top_news()
    
    # Assertions
    assert len(results) <= 5
    assert all(isinstance(item, NewsItem) for item in results)
    assert results[0].score >= results[-1].score  # Check sorting
