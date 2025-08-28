#!/usr/bin/env python3
"""
RAG System API Demo Client
Demonstrates API functionality for the demo video
"""

import requests
import time
import json
from datetime import datetime
from typing import Dict, Any

class RAGApiDemo:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id = f"demo_{int(time.time())}"
    
    def check_health(self) -> bool:
        """Check if API is healthy"""
        try:
            response = requests.get(f"{self.base_url}/healthz", timeout=5)
            if response.status_code:
                print("✅ API Health Check: PASSED")
                return True
            else:
                print(f"❌ API Health Check: FAILED ({response.status_code})")
                return False
        except Exception as e:
            print(f"❌ API Health Check: ERROR - {e}")
            return False
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                print("📊 System Status:")
                print(f"   Documents Indexed: {status.get('ingestion', {}).get('documentCount', 0)}")
                print(f"   Active Sessions: {status.get('activeChatSessions', 0)}")
                return status
            else:
                print(f"❌ Status Check Failed: {response.status_code}")
                return {}
        except Exception as e:
            print(f"❌ Status Error: {e}")
            return {}
    
    def query_rag_system(self, question: str, search_mode: str = "hybrid") -> Dict[str, Any]:
        """Query the RAG system via API"""
        print(f"\n🤔 Question: {question}")
        print(f"🔍 Search Mode: {search_mode}")
        
        payload = {
            "query": question,
            "sessionId": self.session_id,
            "searchMode": search_mode,
            "maxResults": 5
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/query",
                json=payload,
                timeout=60
            )
            end_time = time.time()
            
            response_time = round(end_time - start_time, 2)
            
            if response.status_code == 200:
                result = response.json()
                print(f"⚡ Response Time: {response_time}s")
                print(f"📝 Answer: {result.get('answer', 'No answer')}")
                
                sources = result.get('sources', [])
                if sources:
                    print(f"📚 Sources ({len(sources)}):")
                    for i, source in enumerate(sources[:3], 1):
                        print(f"   {i}. {source.get('title', 'Unknown')} - {source.get('snippet', '')[:100]}...")
                else:
                    print("📚 Sources: None")
                
                return result
            else:
                print(f"❌ Query Failed: {response.status_code} - {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            print(f"❌ Query Error: {e}")
            return {"success": False, "error": str(e)}
    
    def run_demo_sequence(self):
        """Run a complete demo sequence"""
        print("🎬 RAG System API Demo")
        print("=" * 50)
        
        # 1. Health check
        if not self.check_health():
            print("❌ Demo aborted: API not available")
            return
        
        # 2. System status
        self.get_system_status()
        
        # 3. Demo questions
        demo_questions = [
            "What is machine learning?",
        ]
        
        print(f"\n🎯 Demo Session ID: {self.session_id}")
        print(f"📋 Running {len(demo_questions)} demo queries...")
        
        results = []
        for i, question in enumerate(demo_questions, 1):
            print(f"\n--- Query {i}/{len(demo_questions)} ---")
            result = self.query_rag_system(question)
            results.append({
                "question": question,
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
            
            # Brief pause between queries
            if i < len(demo_questions):
                time.sleep(2)
        
        # 4. Demo summary
        print(f"\n📊 Demo Summary:")
        successful_queries = sum(1 for r in results if r["result"].get("success"))
        print(f"   Successful Queries: {successful_queries}/{len(results)}")
        print(f"   Session ID: {self.session_id}")
        print(f"   Total Time: {len(results) * 2} seconds")
        
        # 5. Save demo log
        demo_log = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }
        
        with open(f"demo_log_{self.session_id}.json", "w") as f:
            json.dump(demo_log, f, indent=2)
        
        print(f"💾 Demo log saved: demo_log_{self.session_id}.json")
        print("\n🎉 Demo completed successfully!")

if __name__ == "__main__":
    demo = RAGApiDemo()
    demo.run_demo_sequence()
