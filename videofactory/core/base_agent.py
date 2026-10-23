"""
Abstract Base Agent for VideoFactoryAI Multi-Agent Architecture.
Defines standard interfaces, logging, and error handling for all specialized agents.
"""
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from videofactory.config import VideoFactoryConfig, DEFAULT_CONFIG
from videofactory.core.context import VideoFactoryContext

class BaseAgent(ABC):
    """Base class for all VideoFactoryAI autonomous subagents."""
    
    def __init__(self, name: str = "", config: Optional[VideoFactoryConfig] = None):
        # Infer name from class if not provided
        self._agent_name = name if name else self.__class__.__name__
        self.config = config or DEFAULT_CONFIG

    @property
    def name(self) -> str:
        return self._agent_name

    def log(self, message: str, level: str = "INFO") -> None:
        """Formatted terminal logger."""
        prefixes = {
            "INFO": "[INFO]",
            "SUCCESS": "[OK]",
            "WARN": "[WARN]",
            "ERROR": "[ERROR]"
        }
        prefix = prefixes.get(level, "[INFO]")
        print(f"  {prefix} [{self.name}] {message}")

    def run(self, context: VideoFactoryContext) -> VideoFactoryContext:
        """Standard wrapper around execute with timing and error trapping."""
        start_time = time.time()
        print(f"\n>> [{self.name}] Iniciando execucao...")
        context.log_event(self.name, "Início da execução", status="START")
        
        try:
            context = self.execute(context)
            elapsed = time.time() - start_time
            self.log(f"Concluído com sucesso em {elapsed:.2f}s", level="SUCCESS")
            context.log_event(self.name, f"Concluído em {elapsed:.2f}s", status="SUCCESS")
            return context
        except Exception as e:
            elapsed = time.time() - start_time
            self.log(f"Falha na execução: {e}", level="ERROR")
            context.log_event(self.name, f"Erro: {str(e)}", status="ERROR", data={"error": str(e)})
            raise

    @abstractmethod
    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        """Agent-specific execution logic to be overridden by subclasses."""
        pass
