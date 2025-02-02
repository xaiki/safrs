#!/usr/bin/env python3
# This script is deployed on thomaxxl.pythonanywhere.com
#
# This is a demo application to demonstrate the functionality of the safrs_rest REST API
#
# It can be ran standalone like this:
# python demo_relationship.py [Listener-IP]
#
# This will run the example on http://Listener-Ip:5000
#
# - A database is created and a person is added
# - A rest api is available
# - swagger2 documentation is generated
# - Flask-Admin frontend is created
# - jsonapi-admin pages are served
#
import sys
import os
import datetime
import hashlib
from flask import Flask, redirect, send_from_directory, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_admin import Admin
from flask_admin.contrib import sqla
from safrs import SAFRSAPI  # api factory
from safrs import SAFRSBase  # db Mixin
from safrs import SAFRSFormattedResponse, jsonapi_format_response, log, paginate, ValidationError
from safrs import jsonapi_rpc  # rpc decorator
from safrs import search, startswith  # rpc methods
from flask import url_for, jsonify

description = '''
<a href=http://jsonapi.org>Json-API</a> compliant API built with https://github.com/thomaxxl/safrs <br/>
- <a href="https://github.com/thomaxxl/safrs/blob/master/examples/demo_pythonanywhere_com.py">Source code of this page</a> (less than 200 lines!)<br/>
- <a href="/ja/index.html">reactjs+redux frontend</a>
- <a href="/admin/person">Flask-Admin frontend</a>
- Auto-generated swagger spec: <a href=/swagger.json>swagger.json</a><br/> 
- <a href="/swagger_editor/index.html?url=/swagger.json">Swagger2 Editor</a> (updates can be added with the SAFRSAPI "custom_swagger" argument)
'''

db = SQLAlchemy()
# Add search and startswith methods so we can perform lookups from the frontend
SAFRSBase.search = search
SAFRSBase.startswith = startswith
# Needed because we don't want to implicitly commit when using flask-admin
SAFRSBase.db_commit = False


class Book(SAFRSBase, db.Model):
    """
        description: Book description
    """

    __tablename__ = "Books"
    id = db.Column(db.String, primary_key=True)
    title = db.Column(db.String, default="")
    reader_id = db.Column(db.String, db.ForeignKey("People.id"))
    author_id = db.Column(db.String, db.ForeignKey("People.id"))
    publisher_id = db.Column(db.String, db.ForeignKey("Publishers.id"))
    publisher = db.relationship("Publisher", back_populates="books")
    reviews = db.relationship(
        "Review", backref="book", cascade="save-update, merge, delete, delete-orphan"
    )


class Person(SAFRSBase, db.Model):
    """
        description: People description
    """

    __tablename__ = "People"
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, default="")
    email = db.Column(db.String, default="")
    comment = db.Column(db.Text, default="")
    dob = db.Column(db.Date)
    books_read = db.relationship(
        "Book",
        backref="reader",
        foreign_keys=[Book.reader_id],
        cascade="save-update, merge",
    )
    books_written = db.relationship(
        "Book", backref="author", foreign_keys=[Book.author_id]
    )
    reviews = db.relationship("Review", backref="reader")

    password = db.Column(db.Text, default="")
    exclude_attrs = ["password"]

    # Following methods are exposed through the REST API
    @jsonapi_rpc(http_methods=["POST"])
    def send_mail(self, email):
        """
            description : Send an email
            args:
                email: test email
            parameters:
                - name : my_query_string_param
                  default : my_value
        """
        content = "Mail to {} : {}\n".format(self.name, email)
        with open("/tmp/mail.txt", "a+") as mailfile:
            mailfile.write(content)
        return {"result": "sent {}".format(content)}

    @classmethod
    @jsonapi_rpc(http_methods=["GET","POST"])
    def my_rpc(cls, *args, **kwargs):
        """
            description : Generate and return a jsonapi-formatted response
            pageable: false
            parameters:
                - name : my_query_string_param
                  default : my_value
            args:
                email: test email
        """
        print(args)
        print(kwargs)
        result = cls
        response = SAFRSFormattedResponse()
        try:
            instances = result.query
            links, instances, count = paginate(instances)
            data = [item for item in instances]
            meta = {}
            errors = None
            response.response = jsonapi_format_response(data, meta, links, errors, count)
        except Exception as exc:
            log.exception(exc)

        return response


class Publisher(SAFRSBase, db.Model):
    """
        description: Publisher description
        ---
        demonstrate custom (de)serialization in __init__ and to_dict
    """

    __tablename__ = "Publishers"
    id = db.Column(db.Integer, primary_key=True)  # Integer pk instead of str
    name = db.Column(db.String, default="")
    books = db.relationship("Book", back_populates="publisher")

    def __init__(self, *args, **kwargs):
        custom_field = kwargs.pop("custom_field", None)
        SAFRSBase.__init__(self, **kwargs)

    def to_dict(self):
        result = SAFRSBase.to_dict(self)
        result["custom_field"] = "some customization"
        return result

    @classmethod
    def _s_filter(cls, arg):
        """
            Sample custom filtering, override this method to implement custom filtering
            using the sqlalchemy orm
        """
        return cls.query.filter_by(name=arg)


class Review(SAFRSBase, db.Model):
    """
        description: Review description
    """

    __tablename__ = "Reviews"
    reader_id = db.Column(
        db.String, db.ForeignKey("People.id", ondelete="CASCADE"), primary_key=True
    )
    book_id = db.Column(db.String, db.ForeignKey("Books.id"), primary_key=True)
    review = db.Column(db.String, default="")
    created = db.Column(db.DateTime, default=datetime.datetime.now())


def start_api(HOST="0.0.0.0", PORT=None):

    with app.app_context():
        db.init_app(app)
        db.create_all()
        # populate the database
        for i in range(300):
            secret = hashlib.sha256(bytes(i)).hexdigest()
            reader = Person(name="Reader " + str(i), email="reader_email" + str(i), password=secret)
            author = Person(name="Author " + str(i), email="author_email" + str(i))
            book = Book(title="book_title" + str(i))
            review = Review(
                reader_id=reader.id, book_id=book.id, review="review " + str(i)
            )
            publisher = Publisher(name="name" + str(i))
            publisher.books.append(book)
            reader.books_read.append(book)
            author.books_written.append(book)
            for obj in [reader, author, book, publisher, review]:
                db.session.add(obj)

            db.session.commit()

        swagger_host = HOST
        if PORT and PORT != 80:
            swagger_host += ":{}".format(PORT)

        custom_swagger = {
            "info": {"title": "New Title"},
            "securityDefinitions": {"ApiKeyAuth": {"type": "apiKey" , "in" : "header", "name": "My-ApiKey"}}
        }  # Customized swagger will be merged

        api = SAFRSAPI(
            app,
            host=swagger_host,
            port=PORT,
            prefix=OAS_PREFIX,
            api_spec_url=OAS_PREFIX + "/swagger",
            custom_swagger=custom_swagger,
            schemes=["http", "https"],
            description=description,
        )

        # Flask-Admin Config
        admin = Admin(app, url="/admin")

        for model in [Person, Book, Review, Publisher]:
            # add the flask-admin view
            admin.add_view(sqla.ModelView(model, db.session))
            # Create an API endpoint
            api.expose_object(model)


OAS_PREFIX = "/api"  # swagger location
app = Flask("SAFRS Demo App", template_folder="/home/thomaxxl/mysite/templates")
app.secret_key = "not so secret"
CORS(
    app,
    origins="*",
    allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
    supports_credentials=True,
)

app.config.update(
    SQLALCHEMY_DATABASE_URI="sqlite:////tmp/db", DEBUG=True
)  # DEBUG will also show safrs log messages + exception messages


@app.route("/ja")  # React jsonapi frontend
@app.route("/ja/<path:path>", endpoint="jsonapi_admin")
def send_ja(path="index.html"):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "..", "jsonapi-admin/build"), path
    )


@app.route("/swagger_editor/<path:path>", endpoint="swagger_editor")
def send_swagger_editor(path="index.html"):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "..", "swagger-editor"), path
    )


@app.route("/")
def goto_api():
    return redirect(OAS_PREFIX)


@app.route('/sd')
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return ''

if __name__ == "__main__":
    HOST = sys.argv[1] if len(sys.argv) > 1 else "thomaxxl.pythonanywhere.com"
    PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    start_api(HOST, PORT)
    app.run(host=HOST, port=PORT,threaded=False)
