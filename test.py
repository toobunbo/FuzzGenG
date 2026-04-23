# test_app.py
import gradio as gr

# App vulnerable: trả thẳng user input làm image output
def predict(path: str):
    return path  # str đi thẳng vào postprocess_image(value=path)

demo = gr.Interface(
    fn=predict,
    inputs=gr.Textbox(label="Image path"),
    outputs=gr.Image()
)
demo.launch(server_port=7860)