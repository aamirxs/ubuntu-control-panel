from app.models import ActivityLog
from app.database import init_db
import logging

logger = logging.getLogger(__name__)

async def log_activity(username: str, action: str, ip_address: str, details: str = None):
    """
    Log user activity to the database
    
    Args:
        username: The username performing the action
        action: The action being performed
        ip_address: IP address of the client
        details: Optional details about the action
    """
    try:
        await init_db()
        log_entry = ActivityLog(
            user=username,
            action=action,
            ip_address=ip_address,
            details=details
        )
        await log_entry.save()
        logger.info(f"Activity logged: {username} performed {action} from {ip_address}")
    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def get_user_activities(username: str, limit: int = 100):
    """
    Get activity logs for a specific user
    
    Args:
        username: The username to fetch logs for
        limit: Maximum number of logs to return
        
    Returns:
        List of activity logs
    """
    await init_db()
    logs = await ActivityLog.find(
        {"user": username}
    ).sort("-timestamp").limit(limit).to_list()
    return logs


async def get_all_activities(limit: int = 100):
    """
    Get all activity logs
    
    Args:
        limit: Maximum number of logs to return
        
    Returns:
        List of activity logs
    """
    await init_db()
    logs = await ActivityLog.find().sort("-timestamp").limit(limit).to_list()
    return logs 