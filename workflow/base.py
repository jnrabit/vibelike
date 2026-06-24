"""
Base class for workflow phases.

All workflow phases (Briefing, Planning, Execution, etc.) inherit from this
to provide a consistent interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class WorkflowPhase(ABC):
    """
    Abstract base class for workflow phases.
    
    Each phase takes context from previous phases and produces output
    for the next phase.
    """
    
    def __init__(self, agent=None):
        """
        Initialize phase.
        
        Args:
            agent: Reference to parent WorkflowAgent (for accessing models, retrievers, etc.)
        """
        self.agent = agent
        self.phase_name = self.__class__.__name__.replace('Phase', '')
    
    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the phase.
        
        Args:
            context: Dictionary with results from previous phases
            
        Returns:
            Dictionary with phase results (to be passed to next phase)
        """
        pass
    
    def validate(self, output: Dict[str, Any]) -> bool:
        """
        Validate phase output before returning.
        
        Override in subclasses for custom validation.
        
        Args:
            output: Phase output to validate
            
        Returns:
            True if output is valid, False otherwise
        """
        return bool(output)
    
    def format_output(self, output: Dict[str, Any]) -> str:
        """
        Format phase output for display.
        
        Override in subclasses for custom formatting.
        
        Args:
            output: Phase output
            
        Returns:
            Formatted string for display
        """
        return str(output)


class BriefingPhase(WorkflowPhase):
    """Briefing phase - analyze task and project context."""
    pass


class PlanningStrategyPhase(WorkflowPhase):
    """Planning strategy phase - high-level approach."""
    pass


class PlanningDetailedPhase(WorkflowPhase):
    """Planning detailed phase - concrete implementation steps."""
    pass


class ExecutionPhase(WorkflowPhase):
    """Execution phase - code generation."""
    pass


class VerificationPhase(WorkflowPhase):
    """Verification phase - testing and validation."""
    pass


class FailureAnalysisPhase(WorkflowPhase):
    """Failure analysis phase - diagnose test failures."""
    pass


class CommitPhase(WorkflowPhase):
    """Commit phase - create git commits with changes."""
    pass
