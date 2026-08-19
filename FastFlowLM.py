import json
import socket
import subprocess

try:
    import markdownify
except ImportError:
    markdownify = None
import requests
import time
import re
import base64
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
try:
    from ddgs import DDGS
except ImportError:
    DDGS = None
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
try:
    import selenium
    from selenium import webdriver
    from selenium.webdriver.remote.client_config import ClientConfig
except ImportError:
    selenium = None
    webdriver = None
    ClientConfig = None

JSON_EXPLAIN="why is this json invalid,only give description do not fix it  : "
JSON_FIX="""
Role: You are a Precise JSON Repair Expert. Your sole purpose is to take malformed, "illegal," or broken JSON strings and return a 100% valid, minified JSON object that maintains the original data intent.

Rules of Engagement:

Fix Syntax: Correct missing quotes, unescaped newlines (\n), trailing commas, and improper boolean casing (e.g., change True to true).

Handle Nested Quotes: If a string contains single quotes used as parameters (e.g., command('param')), ensure the outer JSON wrapper uses double quotes (") and internal double quotes are escaped if necessary.
Even if a value has multiple lines the open and close should still be there

Preserve Content: Do not summarize, truncate, or change the information within the values.

Escape Newlines: All physical line breaks within a string must be converted to literal \n characters so the JSON stays on one line if needed.

JSON does not support multi-line strings or triple quotes (''').

In JSON, all strings must be contained on a single line, and any actual line breaks within the string must be represented by the escape sequence \n


Unescaped Double Quotes:
Inside your parameters if it uses " to define the boundaries of the value, you must escape internal quotes with a backslash: \".

Wrong: "print("text")"

Right: "print(\"text\")"
so \"text\" as parameter. not "text". Always make sure to make legal json.

No Prose: Do not explain what was wrong. Do not say "Here is the fixed JSON." Output only the raw JSON object."""



class FastFlowServer:
    def __init__(self, model="qwen3-it:4b", host="127.0.0.1", port=11435,context_window=65536,max_result_tokens=8196,use_selenium=False, selenium=None):
        if selenium is not None:
            use_selenium = selenium
        self.model = model
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}/api/generate"
        self.process = None
        self.convo=[]
        self.last_search_query =""
        self.last_search_results=[]
        self.last_search_region="en_us"
        self.context_window=context_window
        self.current_context=None
        self.max_result_tokens=max_result_tokens
        self.use_selenium=use_selenium
        self.selenium_browser=None
        self.selenium_port=4444
        self.max_consequtive_tools_finished=1
        if self.use_selenium:
            if webdriver is None or ClientConfig is None:
                raise ImportError("Selenium could not be imported, but use_selenium/selenium is set to True. Please install selenium.")
            self.chrome_options = webdriver.ChromeOptions()
            self.chrome_options.add_argument("--no-sandbox")
            self.chrome_options.add_argument("--disable-dev-shm-usage")

    def check_search_dependencies(self):
        missing = []
        if BeautifulSoup is None:
            missing.append("bs4")
        if DDGS is None:
            missing.append("ddgs")
        if self.use_selenium:
            if webdriver is None or ClientConfig is None:
                missing.append("selenium")
        else:
            if sync_playwright is None and (webdriver is None or ClientConfig is None):
                missing.append("playwright or selenium")
            elif sync_playwright is None:
                missing.append("playwright")
        if missing:
            raise ImportError(
                f"Search is enabled (search=True), but required package(s) are not loaded/available: {', '.join(missing)}."
            )
    def escape_custom_chars(self,text):
    # Order matters: replace backslashes first if you were escaping those too
     return text.replace('"', '\\"').replace('[', '\\[').replace('{', '\\{')

    def addconvo_system(self,txt):
        self.convo.append({"role":"system","content":self.escape_custom_chars(txt)})
    def addconvo_user(self,txt):
        self.convo.append({"role":"user","content":self.escape_custom_chars(txt)})
    def addconvo_assistant(self,txt):
        self.convo.append({"role":"assistant","content":self.escape_custom_chars(txt)})

    def list_models(self):
        """Lists available models."""
        try:
            cmd = ["flm", "list"]
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            ml=[]
            for line in iter(self.process.stdout.readline, ""):
                clean_line = line.strip()
                if not " " in clean_line:
                    continue
                arr=clean_line.split(" ")
                if ord(arr[2].strip()[0])==9989:
                    down=True
                else:
                    down=False
                d={"name":arr[1],"downloaded":down}
                ml.append(d)
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
        return ml

    def pull_model(self,model):
        """Lists available models."""
        try:
            cmd = ["flm", "pull",model]
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            ml = []
            for line in iter(self.process.stdout.readline, ""):
                clean_line = line.strip()
                print(clean_line)
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
        return {"error": ""}


    def remove_model(self,model):
        """Lists available models."""
        try:
            print("remove model ",model)
            cmd = ["flm", "remove",model]
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in iter(self.process.stdout.readline, ""):
                clean_line = line.strip()
                print(clean_line)
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
        return {"error": ""}

    def check_selenium(self):
            url = f"http://localhost:{self.selenium_port}/status"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    # Check if the grid is "ready"
                    if status.get('value', {}).get('ready'):
                        print("✅ Selenium is up and ready for sessions.")

                        return True
                    else:
                        print("⚠️ Selenium is starting but not ready yet...")
                else:
                    print(f"❌ Received status {response.status_code}")
            except requests.exceptions.ConnectionError:
                print("❌ Connection refused. Is the Docker container running?")
            return False

    def start_selenium(self):
        try:
            cmd=["docker", "rm", "-f", "selenium-cont"]
            subprocess.run(cmd, check=True)
        except:
            pass
        cmd = ["docker", "run", "-d", "-p", "4444:4444", "--shm-size", "2g", "--name", "selenium-cont", "selenium/standalone-chrome"]
        out=subprocess.run(cmd, check=True)


    def stop_selenium(self):
        try:
            cmd = ["docker", "stop", "selenium-cont"]
            out=subprocess.run(cmd, check=True)
        except:
            pass
        try:
            cmd = ["docker", "rm", "-f", "selenium-cont"]
            subprocess.run(cmd, check=True)

        except:
            pass

    def start(self,downloadifmissing=True):
        """Starts the FastFlowLM server process."""
        if self.use_selenium and not self.check_selenium():
            self.start_selenium()
        print(f"Starting FastFlowLM server with model: {self.model}...")
        # Using the standard flm serve command
        cmd=["fuser"," -k" ,"11435/tcp"]
        if downloadifmissing:
            self.pull_model(self.model)
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cmd = ["flm", "serve",  self.model, "--host", self.host, "--port", str(self.port),"--ctx", str(self.context_window)]
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        for line in iter(self.process.stdout.readline, ""):
            clean_line = line.strip()
            print(f"[FLM-LOG]: {clean_line}")

            # Optional: Auto-detect when the server is ready
            if "Server listening on" in clean_line or "NPU loaded" in clean_line.lower():
                print("\n🚀 NPU SERVER IS READY FOR QUERIES!\n")
                # You could trigger your next logic here
            if "WebServer started" in clean_line:
                break
        print(f"Server should be running at {self.host}:{self.port}")

    def check_fastflowlm(self):
        host=self.host
        port=self.port
        try:
            # Create a socket object
            with socket.create_connection((host, port), timeout=3):
                print(f"Status: Online - FastFlowLM is listening on {host}:{port}")
                return True
        except (ConnectionRefusedError, socket.timeout):
            print(f"Status: Offline - Cannot reach FastFlowLM on {host}:{port}")
            return False
        except Exception as e:
            print(f"Status: Error - {e}")
            return False

    def stop(self):
        """Stops the FastFlowLM server."""
        if self.use_selenium:
            self.stop_selenium()
        if self.process:
            self.process.terminate()
            print("Server stopped.")
            time.sleep(1)
    def extract_response_json(self, text, try_fix=True):
        """
        Extracts the JSON content from a string wrapped in ```json and ```
        and returns it as a dictionary.
        If try_fix is True and parsing fails, it uses the model to fix the JSON.
        """
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
        else:
            json_str = text.strip()

        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            # If standard parsing fails, try cleaning some common issues before asking the model
            try:
                # Basic cleaning: replace single quotes with double quotes (risky but sometimes works for simple cases)
                # or removing trailing commas is more common
                cleaned = re.sub(r',\s*([\]}])', r'\1', json_str)
                cleaned = cleaned.replace("\\", "")
                return json.loads(cleaned)
            except Exception as e:
                estr=str(e)
                if try_fix:
                    max=3
                    for i in range(max):
                        try:
                            problem=self.query_plain(JSON_EXPLAIN+json_str,use_search=False)
                            print(f"JSON parsing failed, attempting to fix with model..."+json_str)
                            fix_prompt = JSON_FIX+f"  the error was {estr}  problem is {problem} and the json is {json_str}"
                            # Call query with try_fix=False to avoid infinite recursion
                            json_str= self.query_plain(fix_prompt,desperate=i,is_json=False,use_search=False)
                            d=json.loads(json_str)
                            return d
                        except Exception as e:
                            estr = str(e)
                            print(f"Attempt {i+1}/{max} failed to fix JSON: {estr}")
                            time.sleep(1)  # brief pause before retrying
            print('could not fix json',json_str)
            return None

    def search_duckduckgo(self, query,region="us-en", max_results=5):
        """
        Queries DuckDuckGo and returns a list of results.
        """
        try:
            with DDGS() as ddgs:
                results = [r for r in ddgs.text(query, region=region,max_results=max_results)]
                self.last_search_results=results
                self.last_search_query=query
                self.last_search_region=region
                return results
        except Exception as e:
            # Try a slightly different approach if context manager fails or returns nothing
            try:
                ddgs = DDGS()
                results = [r for r in ddgs.text(query, max_results=max_results)]
                return results
            except Exception as e2:
                print(f"Error searching DuckDuckGo: {e2}")
                return []

    def download_url_selenium(self,url):
        try:
            from selenium import webdriver
            config = ClientConfig(remote_server_addr=f"http://localhost:{self.selenium_port}", timeout=30)

            self.selenium_browser = webdriver.Remote(
                command_executor=f"http://localhost:{self.selenium_port}/wd/hub",
                options=self.chrome_options,
                client_config=config,
            )
            self.selenium_browser.get(url)
            full_html = self.selenium_browser.page_source
            if BeautifulSoup:
                soup = BeautifulSoup(full_html, 'html.parser')
                body_html = str(soup.body) if soup.body else ""
                text = soup.get_text(separator=' ', strip=True)
            else:
                body_html = full_html
                text = full_html

            if hasattr(self, 'selenium_browser') and self.selenium_browser:
                self.selenium_browser.quit()


            # Get the outer HTML of the selected element and convert it to Markdown
            main_html = str(body_html)
            main_markdown = markdownify.markdownify(main_html) if markdownify else ""

        except Exception as e:
            if hasattr(self, 'selenium_browser') and self.selenium_browser:
                self.selenium_browser.quit()
            return {
            "full_html": "error "+str(e),
            "body_html": "error "+str(e),
            "text": "error "+str(e),
            "markdown": "error "+str(e)
        }

        return {
            "full_html": full_html,
            "body_html": body_html,
            "text": text,
            "markdown": main_markdown
        }

    def download_url(self, url):
        """
        Downloads a URL using Playwright and returns full HTML, body HTML, and just text.
        """
        if self.use_selenium:
            return self.download_url_selenium(url)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded")

                full_html = page.content()

                if BeautifulSoup:
                    soup = BeautifulSoup(full_html, 'html.parser')
                    body_html = str(soup.body) if soup.body else ""
                    text = soup.get_text(separator=' ', strip=True)
                else:
                    body_html = full_html # Fallback
                    text = full_html

                browser.close()
                main_html = str(body_html)
                main_markdown = markdownify.markdownify(main_html) if markdownify else ""
                return {
                    "full_html": full_html,
                    "body_html": body_html,
                    "text": text,
                    "markdown": main_markdown
                }
        except Exception as e:
            print(f"Error downloading URL {url} with Playwright: {e}")
            try:
                print(f"Falling back to requests for {url}")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0'
                }
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                full_html = response.text
                
                if BeautifulSoup:
                    soup = BeautifulSoup(full_html, 'html.parser')
                    body_html = str(soup.body) if soup.body else ""
                    text = soup.get_text(separator=' ', strip=True)
                else:
                    body_html = full_html
                    text = full_html
                
                return {
                    "full_html": full_html,
                    "body_html": body_html,
                    "text": text
                }
            except Exception as e2:
                print(f"Error downloading URL {url} with requests fallback: {e2}")
                return {
                    "full_html": "",
                    "body_html": "",
                    "text": ""
                }

    def audio(self,prompt,audio_path="../input-audio/list-01.wav"):

        # Read the audio and image files and encode them as Base64 for API input
        with open(audio_path, "rb") as audio_file:
            audio = base64.b64encode(audio_file.read()).decode("utf-8")

            client =   client = OpenAI(
            base_url=f"http://{self.host}:{self.port}/v1",
            api_key="not-needed"
            )

        response = client.chat.completions.create(
            model="gemma4-it:e4b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text",
                         "text": prompt},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio},
                        },

                    ],
                }
            ],
            stream=False
        )

        return response.choices[0].message.content
    def query_plain(self, prompt,desperate=0,timeout=180,use_search=True,max_search_results=10,is_json=False,json_sample=None):
        """
        Sends a query to the model and returns the raw response text.
        Optimized for Strix NPU performance.

        """
        if use_search:
            self.check_search_dependencies()

        if is_json:
            if json_sample is None:
                prompt=prompt+" ---- The result has to be in valid json format and put between when no tool call is issued alsways make sure all { and [ are closed ----- "
            else:
                prompt=prompt+" ---- The result has to be in valid json format when no tool call is issued allways make sure all { and [ are closed json according to a scheme like this:  "+str(json_sample)
        if not self.check_fastflowlm():
            self.stop()
            self.start()

        try:
            temp=self.convo.copy()
            self.convo=[]
            if use_search:
                self.addconvo_system("if result not know always looking online with tool if answer is not yet in conversation")
            self.convo.append({"role": "user", "content": prompt})
            resp,extra=self.query_chat(desperate=desperate,is_json=is_json,time_out=timeout,use_search=use_search,max_search_results=max_search_results)
            #response = requests.post(self.url, json=payload, timeout=timeout)
            self.convo=temp.copy()
            if 'error' in resp and extra is None:
                raise Exception(resp)


        except Exception as e:
            return f"error {str(e)}"
        if is_json and isinstance(extra,dict):
            return extra
        else:
            return resp

    def query_chat(self, messages=None,is_json=False,time_out=900,use_search=True,desperate=0,max_search_results=5):

        """
               Sends a query to the model and returns the result as a JSON object.
               Optimized for Strix NPU performance.
               """
        if use_search:
            self.check_search_dependencies()

        if messages is None:
            messages=self.convo
            useconvo=True
        else:
            useconvo=False
        if desperate==0:
            temperature=0
            top_p=0.1
        if desperate == 1:
            temperature = 0.2
            top_p = 0.9
        elif desperate == 2:
           temperature = 0.7
           top_p = 0.9









        try:
            tools = [
                {
                    "name": "search_duckduckgo",
                    "description": "Queries internet search engine DuckDuckGo and returns a list of results.",
                    "parameters": {
                        "type": "object",
                        "properties": {

                            "query": {
                                "type": "string",
                                "description": "The search query to look up on DuckDuckGo."
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return.",
                                "default": max_search_results
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "download_url_text",
                    "description": "Download a webpage from the url and give the text",
                    "parameters": {
                        "type": "object",
                        "properties": {

                            "url": {
                                "type": "string",
                                "description": "the url to download"
                            }
                        },
                        "required": ["url"]
                    }
                }
            ]
            if messages is None:
                messages=self.convo
            if not self.check_fastflowlm():
                self.stop()
                self.start()
            client = OpenAI(
                base_url=f"http://{self.host}:{self.port}/v1",
                api_key="flm"  ,
                timeout=time_out
            )
            if use_search:
                finished=False
                tool_finished=0
                while not finished:
                    if tool_finished>=self.max_consequtive_tools_finished:
                        tools=[]
                    response = client.chat.completions.create(
                        model=self.model,  # Replace with any model you've launched with `flm serve`
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=temperature,
                        top_p=top_p
                    )
                    if  'tool_calls' in response.choices[0].finish_reason:
                        tool_finished+=1
                        for tool_call in response.choices[0].message.tool_calls:
                            if tool_call.function.name=="download_url_text":
                                args = tool_call.function.arguments
                                if isinstance(args, str):
                                    args = json.loads(args)
                                url = args['url']
                                text = self.download_url(url)['text']
                                new_prompt = f"\n\ntext of webpage at  {url}:\n{text}"
                                if useconvo:
                                    self.addconvo_assistant(new_prompt)
                                    messages = self.convo
                                else:
                                    messages.append({"role": "assistant", "content": new_prompt})
                                finished = False

                            if tool_call.function.name == 'search_duckduckgo':
                                args = tool_call.function.arguments
                                if isinstance(args, str):
                                    args = json.loads(args)
                                if 'max_results' not in args or max_search_results>args['max_results']:
                                    args['max_results']=max_search_results
                                search_results = self.search_duckduckgo(**args)
                                # Create a new prompt with the search results and ask again
                                new_prompt = f"\n\nSearch results for {args.get('query')}:\n{json.dumps(search_results)}"
                                if useconvo:
                                    self.addconvo_assistant(new_prompt)
                                    messages = self.convo
                                else:
                                    messages.append({"role": "assistant", "content": new_prompt})
                                finished = False
                    else:
                        finished=True
            else:
                response = client.chat.completions.create(
                    model=self.model,  # Replace with any model you've launched with `flm serve`
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p

                )

            raw_res=response.choices[0].message.content
            res=raw_res
            if is_json:
                try:
                  res=self.extract_response_json(raw_res)
                except:
                  res=None
            return raw_res,res
        except requests.exceptions.RequestException as e:
            return "error"+ str(e), None


    def query_vision(self, prompt, image_path=None, image_url=None, timeout=120):
        """
        Sends a query with an image to the model using the OpenAI compatible endpoint.
        Requires either image_path or image_url.
        Returns: Tuple[full_response_object, content_string]
        """
        if not image_path and not image_url:
            raise ValueError("Either image_path or image_url must be provided.")
        if image_path and image_url:
            raise ValueError("Only one of image_path or image_url can exist.")

        if not self.check_fastflowlm():
            self.stop()
            self.start()

        if image_path:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                # Assuming png format if not specified, or just using a generic data URI
                final_image_url = f"data:image/png;base64,{base64_image}"
        else:
            final_image_url = image_url

        client = OpenAI(
            base_url=f"http://{self.host}:{self.port}/v1",
            api_key="not-needed"
        )

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": final_image_url
                            }
                        },
                    ],
                }
            ],
            timeout=timeout
        )
        
        content = response.choices[0].message.content
        return response, content

    def query_vision_multiple(self, prompt, image_paths=None, image_urls=None, timeout=120):
        """
        Sends a query with multiple images to the model using the OpenAI compatible endpoint.
        Requires either a list of image_paths or a list of image_urls.
        Returns: Tuple[full_response_object, content_string]
        """
        if not image_paths and not image_urls:
            raise ValueError("Either image_paths or image_urls must be provided.")
        if image_paths and image_urls:
            raise ValueError("Only one of image_paths or image_urls can exist.")

        if not self.check_fastflowlm():
            self.stop()
            self.start()

        final_image_urls = []
        if image_paths:
            for path in image_paths:
                with open(path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                    final_image_urls.append(f"data:image/png;base64,{base64_image}")
        else:
            final_image_urls = image_urls

        client = OpenAI(
            base_url=f"http://{self.host}:{self.port}/v1",
            api_key="not-needed"
        )

        content_list = [{"type": "text", "text": prompt}]
        for url in final_image_urls:
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": url
                }
            })

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": content_list,
                }
            ],
            timeout=timeout
        )
        
        content = response.choices[0].message.content
        return response, content





# --- Usage Example ---
if __name__ == "__main__":
    # Initialize the server handler
    ff_server = FastFlowServer(model="qwen3.5:9b",context_window=4096,use_selenium=True)
    try:
        # 1. Start the server
        ff_server.start()
        #super quick sample
        print(ff_server.query_plain("who was einstein"))
        # 2. Define a query
        user_query = """What is the weather forecast for amsterdam """
        json_sample={
  "date": "date of tomorrow",
    "url-info": "https://www.nu.nl/weer",
  "weather": {
    "condition": "Mostly Sunny",
    "temperature_high_celsius": 23,
    "temperature_low_celsius": 11,
    "description": "The weather in Amsterdam forcast (date) is predicted to be mostly sunny with temperatures around 23°C."
  }
}
        # 3. Get results
        print("Querying NPU...")
        raw=ff_server.query_plain(user_query,is_json=True,use_search=True,max_search_results=20,json_sample=json_sample)
        print(raw)
        url=raw["url-info"]
        res=ff_server.download_url(url)['text']
        summary=ff_server.query_plain("make a summary of the text "+res,use_search=False)
        print(summary)

    finally:
        # 6. Ensure the process is killed even if the script crashes
        ff_server.stop()