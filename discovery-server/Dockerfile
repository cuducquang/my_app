FROM maven:3.9.6-eclipse-temurin-8 AS build

WORKDIR /src

# Leverage dependency cache
COPY pom.xml ./
RUN mvn -q -DskipTests dependency:go-offline

COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:8-jre

WORKDIR /app
COPY --from=build /src/target/*.jar /app/app.jar

ENV PORT=8761
EXPOSE 8761

ENTRYPOINT ["java","-jar","/app/app.jar"]


