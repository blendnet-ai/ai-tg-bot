import uuid
from memgpt import create_client
from memgpt.data_types import LLMConfig
from tg_bot.models import AgentConfig


class MemGPTWrapper:
    def __init__(self):
        self.client = create_client()

    def create_agent(self, agent_config_name, user_profile):
        agent_config = AgentConfig.objects.get(name=agent_config_name)
        llm_config = LLMConfig(
            model=agent_config.llm_config["model"],
            model_endpoint_type=agent_config.llm_config["model_endpoint_type"],
            model_endpoint=agent_config.llm_config["model_endpoint"],
            context_window=agent_config.llm_config["context_window"],
        )
        agent_state = self.client.server.create_agent(
            user_id=self.client.user_id,
            name=f"{agent_config.name}-{user_profile.user.id}",
            persona=agent_config.persona_text,
            llm_config=llm_config,
            human=user_profile.get_user_details_for_memgpt(),
            preset=agent_config.memgpt_preset_name,
        )
        return agent_state.id

    def get_agent_config(self, agent_id):
        return self.client.get_agent_config(
            agent_id=uuid.UUID("{" + str(agent_id) + "}")
        )

    def delete_agent(self, agent_id):
        self.client.delete_agent(agent_id)

    def generate_response(self, agent_id, message):
        response = self.client.user_message(agent_id=agent_id, message=message)
        answer = ""
        for r in response:
            if "assistant_message" in r:
                answer += f"ASSISTANT: {r['assistant_message']}\n"
            elif "internal_monologue" in r:
                answer += f"THOUGHTS: {r['internal_monologue']}\n"
        return answer
